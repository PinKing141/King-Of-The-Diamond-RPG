import time
from dataclasses import dataclass
from typing import Optional
from .pitch_logic import resolve_pitch, get_current_catcher
from .ball_in_play import ContactResult, resolve_contact
from .base_running import advance_runners, resolve_steal_attempt
from match_engine.context_manager import get_at_bat_context
from .commentary import (
    display_state,
    announce_pitch,
    announce_play,
    announce_score_change,
    commentary_enabled,
)
from game.rng import get_rng
from game.skill_system import (
    evaluate_situational_skills,
    gather_behavior_tendencies,
    gather_passive_skill_modifiers,
    player_has_skill,
)
from player_roles.fielder_controls import prompt_defensive_shift, SHIFT_LABELS
from match_engine.confidence import (
    adjust_confidence,
    apply_lead_change_swing,
    apply_slump_boost,
    collect_confidence_flashes,
    get_confidence,
    maybe_catcher_settle,
    record_pitcher_stress,
    record_rally_progress,
    reset_rally_tracker,
    reset_slump_chain,
)
from match_engine.states import EventType
from world_sim.baserunning import (
    evaluate_slide_step,
    note_runner_pressure,
    prepare_runner_state,
    simulate_pickoff,
)

rng = get_rng()


def _lineup_slot(player) -> int | None:
    if not player:
        return None
    return getattr(player, "_lineup_slot", getattr(player, "lineup_slot", None))


def _is_cleanup(player) -> bool:
    return _lineup_slot(player) == 4


def _bases_loaded(state) -> bool:
    runners = getattr(state, "runners", None)
    if not runners:
        return False
    return all(runners)


@dataclass
class BuntIntent:
    play: str
    runner_base: int
    target_side: str
    squeeze: bool = False


def _runner_at_base(state, base_index: int):
    runners = getattr(state, "runners", None) or []
    if base_index >= len(runners):
        return None
    return runners[base_index]


def _pitcher_fatigue_level(state, pitcher) -> float:
    if not state or not pitcher:
        return 0.0
    pitcher_id = getattr(pitcher, "id", None)
    pitch_counts = getattr(state, "pitch_counts", {}) or {}
    count = pitch_counts.get(pitcher_id, 0)
    stamina = getattr(pitcher, "stamina", 70) or 70
    stamina = max(45.0, float(stamina))
    fatigue = max(0.0, (count - stamina) / stamina)
    return min(2.0, fatigue)


def _should_slide_step(state, pitcher, runner_threats, fatigue_level: float) -> bool:
    if not runner_threats:
        return False
    threat = runner_threats.get(0) or runner_threats.get(1)
    if not threat:
        return False
    pick_skill = getattr(pitcher, "pickoff_rating", getattr(pitcher, "control", 50)) or 50
    base = 0.18
    base += max(0.0, threat.lead_off_distance - 7.0) * 0.04
    base += threat.jump_quality * 0.02
    base += max(0.0, getattr(state, "pressure_index", 0.0) - 5.0) * 0.02
    base += max(0.0, pick_skill - 55) * 0.002
    base -= fatigue_level * 0.12
    base = max(0.0, min(0.8, base))
    return rng.random() < base


def _apply_slide_step_modifiers(state, pitcher, pitcher_trait_mods, runner_threats):
    fatigue_level = _pitcher_fatigue_level(state, pitcher)
    baseline = evaluate_slide_step(pitcher, use_slide_step=False, fatigue_level=fatigue_level)
    preference = getattr(state, "user_slide_step_mode", "auto")
    if preference == "force_on":
        use_slide = True
    elif preference == "force_off":
        use_slide = False
    else:
        use_slide = _should_slide_step(state, pitcher, runner_threats, fatigue_level)
    if not use_slide:
        state._pending_delivery_time = baseline.delivery_time
        return baseline
    result = evaluate_slide_step(pitcher, use_slide_step=True, fatigue_level=fatigue_level)
    pitcher_trait_mods['control'] = pitcher_trait_mods.get('control', 0) - result.control_penalty
    pitcher_trait_mods['velocity'] = pitcher_trait_mods.get('velocity', 0) - result.velocity_penalty
    state._pending_delivery_time = result.delivery_time
    return result


def _execute_pickoff_attempt(state, pitcher, runner_threats, target_idx: int) -> bool:
    threat = runner_threats.get(target_idx)
    if not threat:
        return False
    outcome = simulate_pickoff(state, threat=threat, pitcher=pitcher)
    cache = getattr(state, "_cached_runner_threats", {}) or {}
    cache.pop(target_idx, None)
    if commentary_enabled():
        pitcher_name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'Pitcher'))
        runner_name = getattr(threat.runner, 'last_name', getattr(threat.runner, 'name', 'Runner'))
        if outcome.picked_runner:
            print(f"   >> {pitcher_name} spins and nails {runner_name}! Pickoff executed.")
        else:
            print(f"   >> {pitcher_name} fires over; {runner_name} dives back safely.")
    if outcome.picked_runner:
        state.runners[threat.base_index] = None
        state.outs += 1
        return True
    return False


def _handle_manual_pickoff_request(state, pitcher, runner_threats) -> bool:
    request = getattr(state, "_manual_pickoff_request", None)
    if not request:
        return False
    state._manual_pickoff_request = None
    target_idx = 0
    if isinstance(request, dict):
        target_idx = request.get("base", 0)
    if target_idx not in runner_threats:
        return False
    return _execute_pickoff_attempt(state, pitcher, runner_threats, target_idx)


def _maybe_call_pickoff_attempt(state, pitcher, runner_threats):
    if not state or not pitcher or not runner_threats:
        return False
    target_idx = 0 if 0 in runner_threats else None
    if target_idx is None:
        return False
    threat = runner_threats[target_idx]
    pick_skill = getattr(pitcher, "pickoff_rating", getattr(pitcher, "control", 50)) or 50
    base = 0.08
    base += max(0.0, threat.lead_off_distance - 7.0) * 0.05
    base += threat.jump_quality * 0.03
    base += max(0.0, pick_skill - 55) * 0.003
    base += max(0.0, getattr(state, "pressure_index", 0.0) - 6.0) * 0.015
    base -= _pitcher_fatigue_level(state, pitcher) * 0.1
    base = max(0.0, min(0.6, base + rng.uniform(-0.02, 0.02)))
    if rng.random() > base:
        return False
    return _execute_pickoff_attempt(state, pitcher, runner_threats, target_idx)


def _capture_runner_threats(state):
    """Publish current runner pressure snapshots for downstream listeners."""
    runners = getattr(state, "runners", None) or []
    cache = {}
    for idx in range(min(3, len(runners))):
        threat = prepare_runner_state(state, idx)
        if threat is None:
            continue
        cache[idx] = threat
        note_runner_pressure(state, threat)
    state._cached_runner_threats = cache
    return cache


def _squeeze_pressure_window(state) -> bool:
    inning = getattr(state, "inning", 1)
    if inning < 7:
        return False
    margin = abs(_offense_margin(state))
    if margin > 2:
        return False
    return True


def _maybe_call_squeeze_play(state, batter, runner_threats):
    if not state or not _squeeze_pressure_window(state):
        return None
    if getattr(state, "outs", 0) >= 2:
        return None
    runner = _runner_at_base(state, 2)
    if not runner:
        return None
    offense_team = state.away_team if state.top_bottom == "Top" else state.home_team
    coach = getattr(offense_team, "coach", None)
    margin = abs(_offense_margin(state))
    base_chance = 0.18 + max(0, getattr(state, "inning", 1) - 6) * 0.02
    if margin <= 1:
        base_chance += 0.1
    elif margin == 2:
        base_chance += 0.05
    pressure = getattr(state, "pressure_index", 0.0) or 0.0
    base_chance += min(0.12, pressure * 0.02)
    if coach:
        volatility = getattr(coach, "volatility", 50) or 50
        drive = getattr(coach, "drive", 50) or 50
        loyalty = getattr(coach, "loyalty", 55) or 55
        base_chance += max(0, volatility - 50) * 0.0015
        base_chance += max(0, drive - 55) * 0.0015
        base_chance += max(0, 60 - loyalty) * 0.001
    if player_has_skill(batter, "bunt_master"):
        base_chance += 0.18
    threat = (runner_threats or {}).get(2)
    if threat:
        base_chance += threat.jump_quality * 0.025
        base_chance += max(0.0, threat.lead_off_distance - 7.0) * 0.015
        base_chance -= max(0.0, threat.pressure) * 0.01
    if getattr(state, "defensive_shift", "normal") == "infield_in":
        base_chance -= 0.15
    base_chance += rng.uniform(-0.04, 0.04)
    base_chance = max(0.0, min(0.9, base_chance))
    if rng.random() > base_chance:
        return None
    target_side = "first" if rng.random() < 0.55 else "third"
    return BuntIntent(play="squeeze", runner_base=2, target_side=target_side, squeeze=True)


def _apply_squeeze_mods(batter_mods, intent: BuntIntent):
    batter_mods['contact_mod'] = batter_mods.get('contact_mod', 0) + 35
    batter_mods['power_mod'] = min(-80, batter_mods.get('power_mod', 0) - 80)
    batter_mods['eye_mod'] = batter_mods.get('eye_mod', 0) + 5
    batter_mods['bunt_flag'] = True
    batter_mods['force_swing'] = True
    batter_mods['bunt_intent'] = intent
    return batter_mods


def _resolve_bunt_contact(state, batter, pitcher, intent: BuntIntent, trait_mods):
    runner = _runner_at_base(state, intent.runner_base)
    if not runner:
        return ContactResult("Out", "Squares early but no runner breaks.", credited_hit=False, special_play=intent.play)
    threat = (getattr(state, "_cached_runner_threats", {}) or {}).get(intent.runner_base)
    contact_skill = (getattr(batter, "contact", 50) or 50) + trait_mods.get('contact', 0)
    if player_has_skill(batter, "bunt_master"):
        contact_skill += 12
    runner_speed = getattr(runner, "speed", 50) or 50
    success = 0.45
    success += (contact_skill - 55) * 0.004
    success += (runner_speed - 60) * 0.003
    if threat:
        success += threat.jump_quality * 0.025
        success += max(0.0, threat.lead_off_distance - 7.0) * 0.01
    pressure = getattr(state, "pressure_index", 0.0) or 0.0
    success += min(0.12, pressure * 0.02)
    if getattr(state, "defensive_shift", "normal") == "infield_in":
        success -= 0.12
    pitcher_fielding = getattr(pitcher, "fielding", getattr(pitcher, "control", 50)) or 50
    success -= max(0, pitcher_fielding - 60) * 0.003
    success = max(0.05, min(0.85, success))
    collapse = 0.18
    roll = rng.random()
    if roll < success:
        moves = [(intent.runner_base, 3, runner)]
        first_runner = _runner_at_base(state, 0)
        if first_runner and getattr(state, "outs", 0) < 2:
            moves.append((0, 1, first_runner))
        hit_chance = 0.12 + max(0.0, contact_skill - 60) * 0.003
        if rng.random() < hit_chance:
            desc = "Drops a perfect squeeze bunt for an infield hit!"
            return ContactResult(
                "1B",
                desc,
                credited_hit=True,
                special_play=intent.play,
                rbi_credit=True,
            )
        desc = "Executes the squeeze! Runner slides home."
        return ContactResult(
            "Out",
            desc,
            credited_hit=False,
            runner_advances=moves,
            special_play=intent.play,
            sacrifice=True,
            rbi_credit=True,
        )
    if roll < success + collapse:
        moves = [(intent.runner_base, -1, runner)]
        desc = "Bunted right back to the pitcher! Runner erased."
        return ContactResult(
            "Out",
            desc,
            credited_hit=False,
            runner_advances=moves,
            special_play=intent.play,
            extra_outs=1,
        )
    desc = "Can't deaden it—popup ends the squeeze."
    return ContactResult("Out", desc, credited_hit=False, special_play=intent.play)


def _apply_runner_advancements(state, assignments):
    if not assignments:
        return 0
    runners = list(getattr(state, "runners", [None, None, None]))
    runs = 0
    for start, dest, runner in assignments:
        if 0 <= start < len(runners) and runners[start] is runner:
            runners[start] = None
        if dest == -1:
            continue
        if dest >= 3:
            runs += 1
        else:
            runners[dest] = runner
    state.runners = runners
    return runs


def _trigger_presence(state, player, trigger_key: str, label: str) -> None:
    system = getattr(state, "presence_system", None)
    if not system or not player:
        return
    player_id = getattr(player, "id", None)
    if not player_id:
        return
    profile = system.get_profile(player_id)
    if not profile:
        return
    was_zone = profile.in_zone
    updated = system.register_trigger(player_id, trigger_key)
    if not updated:
        return
    log_fn = getattr(state, "log_aura_event", None)
    if updated.in_zone and not was_zone and callable(log_fn):
        aura_type = "ace_zone" if updated.role == "ACE" else "cleanup_zone"
        log_fn(
            {
                "type": aura_type,
                "player_id": updated.player_id,
                "team_id": updated.team_id,
                "mode": updated.trust_state(),
                "trigger": label,
            }
        )


def _reset_plate_summary(state):
    state.umpire_plate_summary = {
        "offense": {"favored": 0, "squeezed": 0},
        "defense": {"favored": 0, "squeezed": 0},
    }


def _plate_pressure(state, role: str) -> int:
    plate = getattr(state, 'umpire_plate_summary', None) or {}
    role_state = plate.get(role, {})
    return int(role_state.get("squeezed", 0) - role_state.get("favored", 0))


def _apply_umpire_pressure_bonus(state, batter, pitcher, outcome: str) -> None:
    pressure_offense = _plate_pressure(state, "offense")
    pressure_defense = _plate_pressure(state, "defense")
    if outcome == "walk":
        if pressure_defense > 1:
            adjust_confidence(state, getattr(pitcher, 'id', None), -2, reason="umpire_squeeze", contagious=False)
        elif pressure_defense < -1:
            adjust_confidence(state, getattr(pitcher, 'id', None), 1, reason="umpire_favor", contagious=False)
        if pressure_offense > 1:
            adjust_confidence(state, getattr(batter, 'id', None), 1, reason="umpire_resolve", contagious=False)
    elif outcome == "strikeout":
        if pressure_offense > 1:
            adjust_confidence(state, getattr(batter, 'id', None), -2, reason="umpire_squeeze", contagious=False)
        elif pressure_offense < -1:
            adjust_confidence(state, getattr(pitcher, 'id', None), 1, reason="umpire_favor", contagious=False)
        if pressure_defense > 1:
            adjust_confidence(state, getattr(pitcher, 'id', None), 1, reason="umpire_resolve", contagious=False)


def _update_pitch_diagnostics(state, pitcher_id, outcome):
    tracker = state.pitcher_diagnostics.setdefault(
        pitcher_id,
        {"pitches": 0, "balls": 0, "last_comment_pitch": 0, "last_k_comment": 0},
    )
    tracker["pitches"] += 1
    if outcome == "Ball":
        tracker["balls"] += 1
    return tracker


def _maybe_comment_on_control(pitcher, tracker):
    if not commentary_enabled():
        return
    total = tracker.get("pitches", 0)
    if total < 12:
        return
    ball_ratio = tracker.get("balls", 0) / max(1, total)
    if ball_ratio < 0.45:
        return
    if total - tracker.get("last_comment_pitch", 0) < 8:
        return
    name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'The pitcher'))
    print(f"   >> {name} is struggling to find the zone right now.")
    tracker["last_comment_pitch"] = total


def _maybe_comment_on_dominance(pitcher, tracker, pitcher_stats):
    if not commentary_enabled():
        return
    strikeouts = int(pitcher_stats.get("strikeouts_pitched", 0))
    if strikeouts < 4 or strikeouts % 3 != 0:
        return
    if tracker.get("last_k_comment", 0) == strikeouts:
        return
    name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'The pitcher'))
    print(f"   >> {name} already has {strikeouts} strikeouts. The hitters look lost.")
    tracker["last_k_comment"] = strikeouts


def _handle_batters_eye_feedback(state, batter, pitch_res):
    payload = getattr(pitch_res, "guess_payload", None)
    if not payload or payload.get("result") not in {"locked_in", "fooled"}:
        return
        history = getattr(state, "batters_eye_history", None)
        if not isinstance(history, list):
            history = []
            state.batters_eye_history = history
        entry = {
            "batter_id": getattr(batter, "id", None),
            "name": getattr(batter, "last_name", getattr(batter, "name", "")),
            "label": payload.get("label"),
            "result": payload["result"],
            "source": payload.get("source", "ai"),
            "inning": getattr(state, "inning", 0),
            "outs": getattr(state, "outs", 0),
            "balls": state.balls,
            "strikes": state.strikes,
        }
        history.append(entry)
        if len(history) > 6:
            del history[0]
    label = payload.get("label") or "that pitch"
    label_txt = label.lower()
    result = payload["result"]
    source = payload.get("source", "ai")
    name = getattr(batter, "last_name", getattr(batter, "name", "The batter"))
    actor = "You" if source == "user" else name
    if result == "locked_in":
        message = f"{actor} sat on {label_txt} and was ready."
    else:
        message = f"{actor} guessed {label_txt} but was fooled."
    if commentary_enabled():
        print(f"   >> {message}")
    logs = getattr(state, "logs", None)
    if isinstance(logs, list):
        logs.append(f"Batter's Eye: {message}")


def _auto_batters_eye_guess(state, batter, pitcher, tendencies=None):
    if not state or not batter or not pitcher:
        return None
    discipline = getattr(batter, "discipline", 50) or 50
    mental = getattr(batter, "mental", 50) or 50
    clutch = getattr(batter, "clutch", 50) or 50
    base = 0.08 + max(0, discipline - 50) / 180 + max(0, mental - 50) / 220
    base += max(0, clutch - 60) / 600
    if player_has_skill(batter, "contact_artist"):
        base += 0.05
    if player_has_skill(batter, "walk_machine"):
        base += 0.04
    if player_has_skill(batter, "tough_out"):
        base += 0.03
    tendencies = tendencies or {}
    aggression = tendencies.get("swing_aggression", 1.0)
    if aggression > 1.1:
        base -= min(0.06, (aggression - 1.1) * 0.07)
    base = max(0.03, min(0.45, base))
    if rng.random() > base:
        return None

    balls, strikes = state.balls, state.strikes
    velocity = getattr(pitcher, "velocity", 130) or 130
    movement = getattr(pitcher, "movement", 50) or 50
    control = getattr(pitcher, "control", 50) or 50
    pressure = getattr(state, "pressure_index", 0.0) or 0.0

    options: list[tuple[float, dict]] = []

    def _add_option(kind, value, label, weight, reason=None):
        if weight <= 0:
            return
        payload = {"kind": kind, "value": value, "label": label, "source": "ai"}
        if reason:
            payload["reason"] = reason
        options.append((weight, payload))

    zone_weight = 0.0
    if balls - strikes >= 2 or (balls >= 3 and strikes <= 1):
        zone_weight = 1.2
    if pressure >= 7.0:
        zone_weight += 0.2
    _add_option("location", "zone", "Challenge Strike", zone_weight, "green light count")

    chase_weight = 0.0
    if strikes >= 2 and balls <= 1:
        chase_weight = 0.9
    _add_option("location", "chase", "Waste Pitch", chase_weight, "protect mode")

    fastball_weight = 1.0 + max(0, velocity - 135) / 40
    _add_option("family", "fastball", "Fastball", fastball_weight, "respecting heat")

    breaker_weight = 0.8 + max(0, movement - 60) / 70
    _add_option("family", "breaker", "Breaking Ball", breaker_weight, "expecting spin")

    offspeed_weight = 0.55 + max(0, control - 60) / 150
    _add_option("family", "offspeed", "Offspeed (Change/Split)", offspeed_weight, "timing change")

    if not options:
        _add_option("family", "fastball", "Fastball", 1.0)

    total = sum(weight for weight, _ in options)
    pick = rng.random() * total
    for weight, payload in options:
        pick -= weight
        if pick <= 0:
            return payload
    return options[-1][1]



def _offense_context(state):
    if state.top_bottom == "Top":
        return state.away_team, state.home_pitcher
    return state.home_team, state.away_pitcher


def _player_team_id(player):
    return getattr(player, 'team_id', getattr(player, 'school_id', None))


def _offense_margin(state) -> int:
    if state.top_bottom == "Top":
        return state.away_score - state.home_score
    return state.home_score - state.away_score


def _collect_trait_mods(player, context) -> dict:
    if not player:
        return {}
    merged = dict(gather_passive_skill_modifiers(player))
    situational, _activated = evaluate_situational_skills(player, context)
    for stat, delta in (situational or {}).items():
        merged[stat] = merged.get(stat, 0.0) + delta
    return merged


def _player_has_milestone(state, player, milestone_key: str) -> bool:
    if not state or not player or not milestone_key:
        return False
    checker = getattr(state, "player_has_milestone", None)
    if callable(checker):
        return checker(getattr(player, 'id', None), milestone_key)
    pid = getattr(player, 'id', None)
    milestones = getattr(state, 'player_milestones', {}) or {}
    entries = milestones.get(pid, [])
    target = milestone_key.lower()
    return any((entry.get("key") or "").lower() == target for entry in entries)


def _maybe_call_milestone_pinch_hit(state, lineup):
    offense_team, _ = _offense_context(state)
    team_id = getattr(offense_team, 'id', None)
    if not team_id or team_id == 1:
        return lineup[0]
    if getattr(state, 'inning', 1) < 7:
        return lineup[0]
    if not any(state.runners[idx] for idx in (1, 2)):
        return lineup[0]
    margin = _offense_margin(state)
    if margin > 1:
        return lineup[0]
    bench_map = getattr(state, 'bench_players', {}) or {}
    bench = bench_map.get(team_id)
    if not bench:
        return lineup[0]
    candidates = [
        p for p in bench
        if _player_has_milestone(state, p, "gap_artist")
        and (getattr(p, 'position', '').lower() != 'pitcher')
    ]
    if not candidates:
        return lineup[0]

    def _pinch_score(player):
        return (getattr(player, 'contact', 0) * 1.1) + (getattr(player, 'power', 0)) + (getattr(player, 'speed', 0) * 0.2)

    pinch = max(candidates, key=_pinch_score)
    bench.remove(pinch)
    previous = lineup[0]
    lineup[0] = pinch
    state.player_lookup[pinch.id] = pinch
    state.player_team_map[pinch.id] = team_id
    state.burned_bench.setdefault(team_id, []).append(previous)
    state.pinch_history.append({
        "team_id": team_id,
        "pinch_id": getattr(pinch, 'id', None),
        "replaced_id": getattr(previous, 'id', None),
        "inning": getattr(state, 'inning', 0),
    })
    if commentary_enabled():
        pinch_name = getattr(pinch, 'last_name', getattr(pinch, 'name', 'Batter'))
        prev_name = getattr(previous, 'last_name', getattr(previous, 'name', 'starter'))
        team_label = getattr(offense_team, 'name', 'Coach')
        print(f"   >> {team_label} summons {pinch_name} (Gap-to-Gap milestone) to hit for {prev_name}.")
    return lineup[0]


def _maybe_call_aggressive_play(state, runner_threats=None):
    """High-volatility coaches occasionally send the runner."""
    offense_team, opp_pitcher = _offense_context(state)
    coach = getattr(offense_team, 'coach', None)
    if coach is None:
        return None

    runner = state.runners[0]
    if not runner or state.runners[1] is not None:
        return None
    # Skip manual/user-controlled teams (legacy assumption: team_id 1)
    if _player_team_id(runner) == 1:
        return None

    volatility = getattr(coach, 'volatility', 50) or 50
    drive = getattr(coach, 'drive', 50) or 50
    loyalty = getattr(coach, 'loyalty', 50) or 50

    base_chance = 0.03
    base_chance += max(0, volatility - 50) * 0.002
    base_chance += max(0, drive - 55) * 0.0015
    base_chance -= max(0, 55 - loyalty) * 0.001
    runner_speed = getattr(runner, 'speed', 50) or 50
    base_chance += max(0, runner_speed - 65) * 0.001

    threat_map = runner_threats or getattr(state, "_cached_runner_threats", {}) or {}
    threat = threat_map.get(0)
    if threat:
        lead_bonus = (threat.lead_off_distance - 7.0) * 0.015
        jump_bonus = threat.jump_quality * 0.02
        pressure_penalty = threat.pressure * 0.008
        base_chance += lead_bonus + jump_bonus - pressure_penalty
    if player_has_skill(runner, "speed_demon"):
        base_chance += 0.025

    pickoff_rating = getattr(opp_pitcher, 'pickoff_rating', None)
    if pickoff_rating is None:
        pickoff_rating = getattr(opp_pitcher, 'control', 50) or 50
    base_chance -= max(0, pickoff_rating - 60) * 0.0015
    base_chance += rng.uniform(-0.02, 0.02)

    if _player_has_milestone(state, runner, "walkoff_spark"):
        base_chance += 0.04
        if commentary_enabled():
            runner_name = getattr(runner, 'last_name', getattr(runner, 'name', 'Runner'))
            print(f"   >> Milestone swagger: {runner_name} earned Walk-off Spark; coach trusts his jump.")

    # Late innings or when trailing nudges aggression upward
    offense_is_away = state.top_bottom == "Top"
    score_diff = (state.away_score - state.home_score) if offense_is_away else (state.home_score - state.away_score)
    if state.inning >= 7 and abs(score_diff) <= 2:
        base_chance += 0.02
    if score_diff < 0:
        base_chance += 0.01

    base_chance = max(0.0, min(0.35, base_chance))
    if rng.random() > base_chance:
        return None

    catcher = get_current_catcher(state)
    success, message = resolve_steal_attempt(
        state,
        runner,
        opp_pitcher,
        catcher,
        "2B",
        delivery_override=getattr(state, "_pending_delivery_time", None),
        pop_override=None,
    )
    if commentary_enabled():
        coach_name = getattr(coach, 'name', 'Coach')
        runner_name = getattr(runner, 'last_name', getattr(runner, 'name', 'Runner'))
        print(f"   >> {coach_name} flashes the steal sign for {runner_name}!")
        print(f"   >> {message}")

    state.runners[0] = None
    if success:
        state.runners[1] = runner
        return "continue"

    state.outs += 1
    return "runner_out"


def _rival_match_context(state):
    return getattr(state, "rival_match_context", None)


def _apply_rivalry_bonus(state, batter_id, pitch_name, eye_stat, contact_stat):
    ctx = _rival_match_context(state)
    if not ctx:
        return eye_stat, contact_stat
    bonus = ctx.recognition_bonus(batter_id, pitch_name)
    if not bonus:
        return eye_stat, contact_stat
    multiplier = 1.0 + bonus
    return eye_stat * multiplier, contact_stat * multiplier


def _note_rivalry_strikeout(state, batter_id, pitcher_id, result):
    ctx = _rival_match_context(state)
    if not ctx or not result:
        return
    ctx.note_strikeout(batter_id, pitcher_id, getattr(result, "pitch_name", None))


def _advance_on_wild_pitch(state):
    """Advance all runners one base on a wild pitch, return runs scored."""
    new_runners = [None, None, None]
    runs = 0
    for base in range(2, -1, -1):
        runner = state.runners[base]
        if not runner:
            continue
        dest = base + 1
        if dest >= 3:
            runs += 1
        else:
            new_runners[dest] = runner
    state.runners = new_runners
    return runs


def _defense_team_id(state):
    return state.home_team.id if state.top_bottom == "Top" else state.away_team.id


def _offense_team_id(state):
    return state.away_team.id if state.top_bottom == "Top" else state.home_team.id


def _user_controls_defense(state):
    return _defense_team_id(state) == 1


def _catcher_trusts_shift(state):
    if not _user_controls_defense(state):
        return False
    catcher = get_current_catcher(state)
    if not catcher:
        return False
    trust = getattr(catcher, "trust_baseline", 50) or 50
    return trust >= 55


def _auto_defensive_shift_choice(state):
    runners = getattr(state, "runners", [None, None, None])
    outs = getattr(state, "outs", 0)
    inning = getattr(state, "inning", 1)
    margin = abs(_offense_margin(state))
    if runners[2] and outs <= 1:
        return "infield_in"
    if runners[0] and outs <= 1:
        return "double_play"
    if inning >= 8 and margin <= 2:
        return "deep_outfield"
    return "normal"


def _configure_defensive_shift(state):
    current = getattr(state, "defensive_shift", "normal")
    if _catcher_trusts_shift(state):
        new_shift = prompt_defensive_shift(current)
        source = "User catcher"
    else:
        new_shift = _auto_defensive_shift_choice(state)
        source = "Bench call"
    state.defensive_shift = new_shift
    if new_shift != current:
        label = SHIFT_LABELS.get(new_shift, "Standard Alignment")
        _log_field_general(state, f"{source} sets defense to {label}.")


def _log_field_general(state, message: str) -> None:
    logs = getattr(state, "logs", None)
    if not isinstance(logs, list):
        return
    inning = getattr(state, "inning", 0)
    half = getattr(state, "top_bottom", "Top")
    logs.append(f"[Field General] {message} (Inning {half} {inning})")


def _lead_changed(state, runs_scored, pre_home, pre_away):
    if runs_scored <= 0:
        return False
    if state.top_bottom == "Top":
        before = pre_away - pre_home
        after = (pre_away + runs_scored) - pre_home
    else:
        before = pre_home - pre_away
        after = (pre_home + runs_scored) - pre_away
    return before <= 0 and after > 0


def _apply_walk_confidence(state, batter, pitcher):
    adjust_confidence(state, getattr(batter, 'id', None), 2, reason="discipline")
    adjust_confidence(state, getattr(pitcher, 'id', None), -2, reason="discipline")
    _apply_umpire_pressure_bonus(state, batter, pitcher, "walk")


def _apply_strikeout_confidence(state, batter, pitcher):
    adjust_confidence(state, getattr(batter, 'id', None), -8, reason="strikeout")
    adjust_confidence(state, getattr(pitcher, 'id', None), 4, reason="strikeout")
    _apply_umpire_pressure_bonus(state, batter, pitcher, "strikeout")


def _apply_contact_confidence(state, batter, pitcher, contact_res):
    if contact_res.hit_type == "Out":
        adjust_confidence(state, getattr(batter, 'id', None), -4, reason="out")
        adjust_confidence(state, getattr(pitcher, 'id', None), 3, reason="heroics")
        return
    boosts = {"1B": 5, "2B": 7, "3B": 9, "HR": 12}
    base = boosts.get(contact_res.hit_type, 4)
    if not contact_res.credited_hit:
        base = max(2, base - 3)
    adjust_confidence(state, getattr(batter, 'id', None), base, reason="clutch_hit")
    adjust_confidence(state, getattr(pitcher, 'id', None), -min(base, 8), reason="hit_allowed")


def _broadcast_confidence_flashes(state):
    if not commentary_enabled():
        collect_confidence_flashes(state)
        return
    for event in collect_confidence_flashes(state):
        direction = "surging" if event["delta"] > 0 else "reeling"
        magnitude = f"{event['delta']:+.0f}"
        reason = event.get("reason") or "moment"
        inning = event.get("inning") or getattr(state, "inning", 0)
        print(f"   >> Confidence pulse ({inning}): {event['name']} is {direction} ({magnitude}, {reason}).")


def _handle_argument_event(state, pitch_res, batter, pitcher):
    label = getattr(pitch_res, 'special', None)
    if label not in {"argument_batter", "argument_pitcher"}:
        return
    penalty = getattr(pitch_res, 'argument_penalty', 0) or 0
    target = batter if label == "argument_batter" else pitcher
    target_id = getattr(target, 'id', None)
    ejected = getattr(pitch_res, 'argument_ejection', False)
    if penalty > 0:
        adjust_confidence(state, target_id, -penalty, reason="ump_argument", contagious=False)
        morale = getattr(target, 'morale', 60) or 60
        morale -= max(1, penalty // 2)
        target.morale = max(15, morale)
        if commentary_enabled():
            name = getattr(target, 'last_name', getattr(target, 'name', 'Player'))
            print(f"   >> {name} barks at the ump and gets rattled ({penalty} confidence hit).")
    if ejected:
        _record_ejection(state, target, label)


def _record_ejection(state, player, label):
    if not player:
        return
    pid = getattr(player, 'id', None)
    team_id = state.player_team_map.get(pid) if hasattr(state, 'player_team_map') else None
    adjust_confidence(state, pid, -22, reason="ejected", contagious=False)
    if team_id:
        for mate in state.team_rosters.get(team_id, []):
            if mate and getattr(mate, 'id', None) != pid:
                adjust_confidence(state, mate.id, -4, reason="ejected", contagious=False)
    morale = getattr(player, 'morale', 60) or 60
    player.morale = max(5, morale - 25)
    getattr(state, 'ejections', []).append({
        "player_id": pid,
        "team_id": team_id,
        "inning": getattr(state, 'inning', 0),
        "role": label,
    })
    if commentary_enabled():
        name = getattr(player, 'last_name', getattr(player, 'name', 'Player'))
        print(f"   >> {name} is tossed after the argument! Umpire patience ran out.")

class AtBatStateMachine:
    STATE_WINDUP = "STATE_WINDUP"
    STATE_PITCH_FLIGHT = "STATE_PITCH_FLIGHT"
    STATE_CONTACT = "STATE_CONTACT"
    STATE_RESOLVE = "STATE_RESOLVE"

    def __init__(self, state):
        self.state = state
        self.bus = getattr(state, "event_bus", None)

    def _emit_state(self, state_name: str, payload: Optional[dict[str, object]] = None) -> None:
        if self.bus:
            data = payload or {}
            data.setdefault("state", state_name)
            self.bus.publish("MATCH_STATE_CHANGE", data)

    def run(self):
        """
        Simulates one complete At-Bat.
        Returns True if the inning continues, False if 3 outs reached immediately.
        """
        state = self.state
        pitcher = state.home_pitcher if state.top_bottom == "Top" else state.away_pitcher
        lineup = state.away_lineup if state.top_bottom == "Top" else state.home_lineup
        batter = lineup[0]
        batter = _maybe_call_milestone_pinch_hit(state, lineup)
        lineup[0] = batter
        batting_team = state.away_team if state.top_bottom == "Top" else state.home_team
        offense_team_id = _offense_team_id(state)
        batter_id = getattr(batter, 'id', None)
        pitcher_id = getattr(pitcher, 'id', None)

        last_pitch_res = None
        pressure_updater = getattr(state, "update_pressure_index", None)
        if callable(pressure_updater):
            pressure_updater()
        
        state.reset_count()
        state.defensive_shift = "normal"
        _reset_plate_summary(state)
        batter_stats = state.get_stats(batter.id)
        pitcher_stats = state.get_stats(pitcher.id)
        state.latest_play_detail = None
        if commentary_enabled():
            display_state(state, pitcher, batter)
        
        batter_tendencies = gather_behavior_tendencies(batter)
        times_faced = state.register_plate_appearance(pitcher_id, batter_id)
        steal_checked = False
        squeeze_called = False
        while True:
            self._emit_state(self.STATE_WINDUP, {
                "inning": state.inning,
                "half": state.top_bottom,
                "batter_id": batter_id,
                "pitcher_id": pitcher_id,
            })
            # --- USER INPUT CHECK (BATTER) ---
            batter_action = "Normal"
            batter_mods = {}
            
            # Check if Batter is USER (Assuming Team ID 1 is User)
            if _player_team_id(batter) == 1:
                from player_roles.batter_controls import player_bat_turn
                batter_action, batter_mods = player_bat_turn(pitcher, batter, state)
            else:
                guess_payload = _auto_batters_eye_guess(state, batter, pitcher, batter_tendencies)
                if guess_payload:
                    batter_mods['guess_payload'] = guess_payload

            defense_runners = getattr(state, "runners", None) or []
            if _user_controls_defense(state) and any(defense_runners[:2]):
                from player_roles.pitcher_controls import prompt_runner_threat_controls
                prompt_runner_threat_controls(pitcher, state)

            state._pending_delivery_time = None
            slide_trait_mods = {}
            runner_threats = _capture_runner_threats(state)
            slide_profile = None
            if runner_threats:
                if _handle_manual_pickoff_request(state, pitcher, runner_threats):
                    if state.outs >= 3:
                        return
                    continue
                slide_profile = _apply_slide_step_modifiers(state, pitcher, slide_trait_mods, runner_threats)
                if _maybe_call_pickoff_attempt(state, pitcher, runner_threats):
                    if state.outs >= 3:
                        return
                    continue
            else:
                state._pending_delivery_time = None
            squeeze_intent = None
            if not squeeze_called and _player_team_id(batter) != 1:
                squeeze_intent = _maybe_call_squeeze_play(state, batter, runner_threats)
                if squeeze_intent:
                    squeeze_called = True
                    batter_action = "Bunt"
                    _apply_squeeze_mods(batter_mods, squeeze_intent)
                    if self.bus:
                        self.bus.publish(
                            EventType.OFFENSE_CALLS_SQUEEZE.value,
                            {
                                "inning": state.inning,
                                "half": state.top_bottom,
                                "batter_id": batter_id,
                                "runner_id": getattr(_runner_at_base(state, squeeze_intent.runner_base), "id", None),
                                "team_id": getattr(batting_team, 'id', None),
                            },
                        )
                    if commentary_enabled():
                        team_name = getattr(batting_team, 'name', 'Coach')
                        print(f"   >> {team_name} flashes the squeeze! Runner breaks for home.")

            if not steal_checked:
                steal_result = _maybe_call_aggressive_play(state, runner_threats)
                steal_checked = True
                if steal_result == "runner_out":
                    if state.outs >= 3:
                        return
                    continue

            trait_context = get_at_bat_context(state, batter, pitcher)
            batter_trait_mods = _collect_trait_mods(batter, trait_context)
            pitcher_trait_mods = _collect_trait_mods(pitcher, trait_context)
            if slide_trait_mods:
                for key, delta in slide_trait_mods.items():
                    pitcher_trait_mods[key] = pitcher_trait_mods.get(key, 0) + delta

            _configure_defensive_shift(state)

            bases_loaded_snapshot = _bases_loaded(state)
            outs_snapshot = state.outs

            # 1. Pitch Resolution (Pass batter intent)
            self._emit_state(self.STATE_PITCH_FLIGHT, {
                "inning": state.inning,
                "half": state.top_bottom,
                "balls": state.balls,
                "strikes": state.strikes,
            })
            state.add_pitch_count(pitcher.id)
            pitch_res = resolve_pitch(
                pitcher,
                batter,
                state,
                batter_action,
                batter_mods,
                batter_trait_mods=batter_trait_mods,
                pitcher_trait_mods=pitcher_trait_mods,
                batter_tendencies=batter_tendencies,
                times_through_order=times_faced,
            )
            last_pitch_res = pitch_res
            tracker = _update_pitch_diagnostics(state, pitcher.id, pitch_res.outcome)

            announce_pitch(pitch_res)
            _maybe_comment_on_control(pitcher, tracker)
            _handle_argument_event(state, pitch_res, batter, pitcher)
            _handle_batters_eye_feedback(state, batter, pitch_res)
            
            # 2. Update Count
            self._emit_state(self.STATE_RESOLVE, {
                "outcome": pitch_res.outcome,
                "inning": state.inning,
                "half": state.top_bottom,
            })
            if pitch_res.outcome == "Ball":
                state.balls += 1
                if getattr(pitch_res, 'special', None) == "wild_pitch":
                    if commentary_enabled():
                        print("   >> Wild pitch! Everyone moves up 90 feet.")
                    wild_runs = _advance_on_wild_pitch(state)
                    if wild_runs:
                        announce_score_change(wild_runs, getattr(batting_team, 'name', 'Unknown School'))
                        if state.top_bottom == "Top":
                            state.away_score += wild_runs
                        else:
                            state.home_score += wild_runs
                        pitcher_stats["runs_allowed"] += wild_runs
                    adjust_confidence(state, getattr(pitcher, 'id', None), -6, reason="wild_pitch")
                    catcher = get_current_catcher(state)
                    if catcher:
                        adjust_confidence(state, getattr(catcher, 'id', None), -3, reason="wild_pitch", contagious=False)
                    record_pitcher_stress(state, pitcher_id, spike=True)
                    maybe_catcher_settle(state, pitcher_id)
                    if state.balls == 4:
                        if commentary_enabled():
                            print("   >> WALK.")
                        was_slumping = get_confidence(state, batter_id) <= -30
                        state.runners[0] = batter 
                        batter_stats["walks"] += 1
                        pitcher_stats["walks"] += 1
                        _apply_walk_confidence(state, batter, pitcher)
                        record_pitcher_stress(state, pitcher_id, spike=True)
                        record_rally_progress(state, offense_team_id, batter_id, reached_base=True)
                        apply_slump_boost(state, batter_id, was_slumping, "walk")
                        maybe_catcher_settle(state, pitcher_id)
                        _trigger_presence(state, pitcher, "walk_batter", "Issued Walk")
                    break
                    
            elif pitch_res.outcome == "Strike":
                if state.strikes < 2 or pitch_res.description != "Foul": 
                    state.strikes += 1
                
                if state.strikes == 3:
                    if commentary_enabled():
                        print("   >> STRIKEOUT!")
                    state.outs += 1
                    batter_stats["strikeouts"] += 1
                    pitcher_stats["strikeouts_pitched"] += 1
                    if last_pitch_res and getattr(last_pitch_res, "full_count", False):
                        _trigger_presence(state, pitcher, "strikeout_full_count", "Full Count K")
                    if bases_loaded_snapshot and outs_snapshot == 2:
                        _trigger_presence(state, pitcher, "escape_bases_loaded", "Bases Loaded Escape")
                    if _is_cleanup(batter):
                        trigger_label = "Cleanup Silenced"
                        if last_pitch_res and last_pitch_res.description == "Swinging Miss":
                            _trigger_presence(state, batter, "strikeout_swinging", "Cleanup Whiffs")
                            trigger_label = "Cleanup Chased"
                        _trigger_presence(state, pitcher, "strikeout_cleanup", trigger_label)
                    _maybe_comment_on_dominance(pitcher, tracker, pitcher_stats)
                    _apply_strikeout_confidence(state, batter, pitcher)
                    reset_slump_chain(state, batter_id)
                    record_pitcher_stress(state, pitcher_id, spike=False)
                    reset_rally_tracker(state, offense_team_id)
                    _note_rivalry_strikeout(state, batter_id, pitcher_id, last_pitch_res)
                    break
                    
            elif pitch_res.outcome == "Foul":
                if state.strikes < 2:
                    state.strikes += 1
                    
            elif pitch_res.outcome == "InPlay":
                self._emit_state(self.STATE_CONTACT, {
                    "inning": state.inning,
                    "half": state.top_bottom,
                    "quality": pitch_res.contact_quality,
                })
                # 3. Contact
                p_mod = getattr(pitch_res, 'power_mod', 0)
                bunt_intent = getattr(pitch_res, "bunt_intent", None)
                if bunt_intent and getattr(bunt_intent, "squeeze", False):
                    contact_res = _resolve_bunt_contact(state, batter, pitcher, bunt_intent, batter_trait_mods)
                else:
                    contact_res = resolve_contact(
                        pitch_res.contact_quality,
                        batter,
                        pitcher,
                        state,
                        power_mod=p_mod,
                        trait_mods=batter_trait_mods,
                    )
                announce_play(contact_res)
                reached_base = contact_res.hit_type != "Out"
                was_slumping = reached_base and get_confidence(state, batter_id) <= -30
                _apply_contact_confidence(state, batter, pitcher, contact_res)
                error_flag = bool(getattr(contact_res, "error_on_play", False))

                if contact_res.hit_type != "Out" and getattr(batter, "position", "").lower() == "pitcher":
                    _trigger_presence(state, pitcher, "hit_allowed_to_pitcher", "Pitcher Hit Allowed")
                if contact_res.hit_type != "Out" and _is_cleanup(batter) and contact_res.hit_type in {"2B", "3B", "HR"}:
                    _trigger_presence(state, batter, "extra_base_hit", "Cleanup Slug")

                runs_scored_on_play = 0
                if contact_res.hit_type == "Out":
                    outs_recorded = 1 + int(getattr(contact_res, "extra_outs", 0))
                    state.outs += outs_recorded
                    if not getattr(contact_res, "sacrifice", False):
                        batter_stats["at_bats"] += 1
                    pitcher_stats["innings_pitched"] += 0.33 * outs_recorded
                    reset_slump_chain(state, batter_id)
                    record_pitcher_stress(state, pitcher_id, spike=False)
                    reset_rally_tracker(state, offense_team_id)
                else:
                    batter_stats["at_bats"] += 1
                    if contact_res.credited_hit:
                        batter_stats["hits"] += 1
                    if contact_res.hit_type == "HR" and contact_res.credited_hit:
                        batter_stats["homeruns"] += 1

                    pre_home = state.home_score
                    pre_away = state.away_score
                    runs = advance_runners(state, contact_res.hit_type, batter)
                    lead_change = _lead_changed(state, runs, pre_home, pre_away)
                    runs_scored_on_play = runs

                    if runs > 0:
                        announce_score_change(runs, getattr(batting_team, 'name', 'Unknown School'))
                        if state.top_bottom == "Top":
                            state.away_score += runs
                        else:
                            state.home_score += runs

                        if contact_res.credited_hit:
                            batter_stats["rbi"] += runs
                        pitcher_stats["runs_allowed"] += runs
                        if lead_change:
                            apply_lead_change_swing(state)
                    if runs > 0 and _is_cleanup(batter):
                        _trigger_presence(state, batter, "rbi", "Cleanup RBI")

                    record_pitcher_stress(state, pitcher_id, spike=True)
                    record_rally_progress(state, offense_team_id, batter_id, reached_base=True)
                    apply_slump_boost(state, batter_id, was_slumping, "hit")
                    maybe_catcher_settle(state, pitcher_id)

                advances = getattr(contact_res, "runner_advances", None)
                if advances:
                    pre_home_adv = state.home_score
                    pre_away_adv = state.away_score
                    extra_runs = _apply_runner_advancements(state, advances)
                    if extra_runs:
                        runs_scored_on_play += extra_runs
                        announce_score_change(extra_runs, getattr(batting_team, 'name', 'Unknown School'))
                        if state.top_bottom == "Top":
                            state.away_score += extra_runs
                        else:
                            state.home_score += extra_runs
                        if getattr(contact_res, "rbi_credit", False):
                            batter_stats["rbi"] += extra_runs
                        pitcher_stats["runs_allowed"] += extra_runs
                        if _lead_changed(state, extra_runs, pre_home_adv, pre_away_adv):
                            apply_lead_change_swing(state)

                outs_logged = max(0, state.outs - outs_snapshot)
                state.latest_play_detail = {
                    "hit_type": contact_res.hit_type,
                    "outs_on_play": outs_logged,
                    "double_play": outs_logged >= 2 and contact_res.hit_type == "Out",
                    "runs_scored": runs_scored_on_play,
                    "description": contact_res.description,
                    "credited_hit": contact_res.credited_hit,
                    "error_on_play": error_flag,
                    "error_type": getattr(contact_res, "error_type", None),
                    "error_position": getattr(contact_res, "primary_position", None),
                }

                break

        if callable(pressure_updater):
            pressure_updater()
        _broadcast_confidence_flashes(state)
        return


def start_at_bat(state):
    machine = AtBatStateMachine(state)
    machine.run()