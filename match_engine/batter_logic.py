import time
from .pitch_logic import resolve_pitch, get_current_catcher
from .ball_in_play import resolve_contact
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

rng = get_rng()


def _record_momentum(state, team_id, event_key: str) -> None:
    system = getattr(state, "momentum_system", None)
    if system and team_id is not None:
        system.record_event(team_id, event_key)


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


def get_recent_batters_eye_history(state, *, max_items: int = 3):
    history = getattr(state, "batters_eye_history", None) or []
    return list(history[-max_items:])
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


def _maybe_call_aggressive_play(state):
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
    success, message = resolve_steal_attempt(state, runner, opp_pitcher, catcher, "2B")
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

def start_at_bat(state):
    """
    Simulates one complete At-Bat.
    Returns True if the inning continues, False if 3 outs reached immediately.
    """
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
    if commentary_enabled():
        display_state(state, pitcher, batter)
    
    batter_tendencies = gather_behavior_tendencies(batter)
    times_faced = state.register_plate_appearance(pitcher_id, batter_id)
    steal_checked = False
    while True:
        # time.sleep(0.5) # Pace the game
        
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
        
        if not steal_checked:
            steal_result = _maybe_call_aggressive_play(state)
            steal_checked = True
            if steal_result == "runner_out":
                if state.outs >= 3:
                    return
                continue

        trait_context = get_at_bat_context(state, batter, pitcher)
        batter_trait_mods = _collect_trait_mods(batter, trait_context)
        pitcher_trait_mods = _collect_trait_mods(pitcher, trait_context)

        _configure_defensive_shift(state)

        bases_loaded_snapshot = _bases_loaded(state)
        outs_snapshot = state.outs

        # 1. Pitch Resolution (Pass batter intent)
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
                _record_momentum(state, _defense_team_id(state), "strikeout")
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
                break
                
        elif pitch_res.outcome == "Foul":
            if state.strikes < 2:
                state.strikes += 1
                
        elif pitch_res.outcome == "InPlay":
            # 3. Contact
            p_mod = getattr(pitch_res, 'power_mod', 0)
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
            if contact_res.error_on_play:
                _record_momentum(state, _defense_team_id(state), "error")

            if contact_res.hit_type != "Out" and getattr(batter, "position", "").lower() == "pitcher":
                _trigger_presence(state, pitcher, "hit_allowed_to_pitcher", "Pitcher Hit Allowed")
            if contact_res.hit_type != "Out" and _is_cleanup(batter) and contact_res.hit_type in {"2B", "3B", "HR"}:
                _trigger_presence(state, batter, "extra_base_hit", "Cleanup Slug")

            if contact_res.hit_type == "Out":
                state.outs += 1
                batter_stats["at_bats"] += 1
                pitcher_stats["innings_pitched"] += 0.33
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

            break

    if callable(pressure_updater):
        pressure_updater()
    _broadcast_confidence_flashes(state)
    return