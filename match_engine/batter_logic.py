import time
from dataclasses import dataclass
from enum import Enum, auto
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
from match_engine.pitch_definitions import PITCH_TYPES
from game.mechanics.strike_zone_renderer import build_pitch_snapshot_lines
from core.rng import get_rng
try:
    from game.config_loader import ConfigLoader
except Exception:
    class ConfigLoader:  # type: ignore
        @staticmethod
        def get_section(section: str, default=None):
            return default if default is not None else {}
from game.mechanics.skill_system import (
    evaluate_situational_skills,
    gather_behavior_tendencies,
    gather_passive_skill_modifiers,
    player_has_skill,
)
from battery_system.battery_trust import adjust_battery_sync
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
from match_engine.states import EventType, HitType, PlayMode
from world_sim.baserunning import (
    evaluate_slide_step,
    note_runner_pressure,
    prepare_runner_state,
    simulate_pickoff,
)

rng = get_rng()
_TUNING = ConfigLoader.get_section("batter_logic", default={}) or {}


def _tune(key: str, default):
    return _TUNING.get(key, default)


# Tuning constants (override via data/balancing.json -> "batter_logic" section)
SQUEEZE_BASE = _tune("squeeze_base", 0.18)
SQUEEZE_INNING_SCALE = _tune("squeeze_inning_scale", 0.02)
SQUEEZE_MARGIN_CLOSE_BONUS = _tune("squeeze_margin_close_bonus", 0.10)
SQUEEZE_MARGIN_TWO_BONUS = _tune("squeeze_margin_two_bonus", 0.05)
SQUEEZE_PRESSURE_SCALE = _tune("squeeze_pressure_scale", 0.02)
SQUEEZE_VOLATILITY_SCALE = _tune("squeeze_volatility_scale", 0.0015)
SQUEEZE_DRIVE_SCALE = _tune("squeeze_drive_scale", 0.0015)
SQUEEZE_LOYALTY_SCALE = _tune("squeeze_loyalty_scale", 0.001)
SQUEEZE_BUNT_MASTER_BONUS = _tune("squeeze_bunt_master_bonus", 0.18)
SQUEEZE_JUMP_SCALE = _tune("squeeze_jump_scale", 0.025)
SQUEEZE_LEAD_SCALE = _tune("squeeze_lead_scale", 0.015)
SQUEEZE_PRESSURE_PENALTY = _tune("squeeze_pressure_penalty", 0.01)
SQUEEZE_INFIELD_IN_PENALTY = _tune("squeeze_infield_in_penalty", 0.15)
SQUEEZE_RNG_DELTA = _tune("squeeze_rng_delta", 0.04)
SQUEEZE_MAX = _tune("squeeze_max", 0.9)

STEAL_BASE = _tune("steal_base", 0.03)
STEAL_VOLATILITY_SCALE = _tune("steal_volatility_scale", 0.002)
STEAL_DRIVE_SCALE = _tune("steal_drive_scale", 0.0015)
STEAL_LOYALTY_SCALE = _tune("steal_loyalty_scale", 0.001)
STEAL_SPEED_SCALE = _tune("steal_speed_scale", 0.001)
STEAL_PICKOFF_PENALTY = _tune("steal_pickoff_penalty", 0.0015)
STEAL_JUMP_SCALE = _tune("steal_jump_scale", 0.02)
STEAL_LEAD_SCALE = _tune("steal_lead_scale", 0.015)
STEAL_PRESSURE_PENALTY = _tune("steal_pressure_penalty", 0.008)
STEAL_WALKOFF_BONUS = _tune("steal_walkoff_bonus", 0.04)
STEAL_LATE_INNING_BONUS = _tune("steal_late_inning_bonus", 0.02)
STEAL_TRAILING_BONUS = _tune("steal_trailing_bonus", 0.01)
STEAL_RNG_DELTA = _tune("steal_rng_delta", 0.02)
STEAL_MAX = _tune("steal_max", 0.35)

BUNT_CONTACT_SCALE = _tune("bunt_contact_scale", 0.004)
BUNT_SPEED_SCALE = _tune("bunt_speed_scale", 0.003)
BUNT_JUMP_SCALE = _tune("bunt_jump_scale", 0.025)
BUNT_LEAD_SCALE = _tune("bunt_lead_scale", 0.01)
BUNT_PRESSURE_SCALE = _tune("bunt_pressure_scale", 0.02)
BUNT_FIELDING_PENALTY = _tune("bunt_fielding_penalty", 0.003)
BUNT_MIN_SUCCESS = _tune("bunt_min_success", 0.05)
BUNT_MAX_SUCCESS = _tune("bunt_max_success", 0.85)
BUNT_HIT_BASE = _tune("bunt_hit_base", 0.12)
BUNT_HIT_CONTACT_SCALE = _tune("bunt_hit_contact_scale", 0.003)
BUNT_INFIELD_IN_PENALTY = _tune("bunt_infield_in_penalty", 0.12)

# Batter's eye tuning
BATTERS_EYE_BASE = _tune("batters_eye_base", 0.08)
BATTERS_EYE_DISCIPLINE_SCALE = _tune("batters_eye_discipline_scale", 1 / 180)
BATTERS_EYE_MENTAL_SCALE = _tune("batters_eye_mental_scale", 1 / 220)
BATTERS_EYE_CLUTCH_SCALE = _tune("batters_eye_clutch_scale", 1 / 600)
BATTERS_EYE_CONTACT_ARTIST_BONUS = _tune("batters_eye_contact_artist_bonus", 0.05)
BATTERS_EYE_WALK_MACHINE_BONUS = _tune("batters_eye_walk_machine_bonus", 0.04)
BATTERS_EYE_TOUGH_OUT_BONUS = _tune("batters_eye_tough_out_bonus", 0.03)
BATTERS_EYE_AGGRESSION_THRESHOLD = _tune("batters_eye_aggression_threshold", 1.1)
BATTERS_EYE_AGGRESSION_PENALTY_SCALE = _tune("batters_eye_aggression_penalty_scale", 0.07)
BATTERS_EYE_AGGRESSION_PENALTY_CAP = _tune("batters_eye_aggression_penalty_cap", 0.06)
BATTERS_EYE_MIN = _tune("batters_eye_min", 0.03)
BATTERS_EYE_MAX = _tune("batters_eye_max", 0.45)
BATTERS_EYE_ZONE_WEIGHT = _tune("batters_eye_zone_weight", 1.2)
BATTERS_EYE_ZONE_PRESSURE_THRESHOLD = _tune("batters_eye_zone_pressure_threshold", 7.0)
BATTERS_EYE_ZONE_PRESSURE_BONUS = _tune("batters_eye_zone_pressure_bonus", 0.2)
BATTERS_EYE_ZONE_COUNT_DIFF = _tune("batters_eye_zone_count_diff", 2)
BATTERS_EYE_ZONE_FRIENDLY_BALLS = _tune("batters_eye_zone_friendly_balls", 3)
BATTERS_EYE_ZONE_FRIENDLY_STRIKES = _tune("batters_eye_zone_friendly_strikes", 1)
BATTERS_EYE_CHASE_WEIGHT = _tune("batters_eye_chase_weight", 0.9)
BATTERS_EYE_CHASE_PROTECT_STRIKES = _tune("batters_eye_chase_protect_strikes", 2)
BATTERS_EYE_CHASE_PROTECT_BALLS = _tune("batters_eye_chase_protect_balls", 1)
BATTERS_EYE_FASTBALL_WEIGHT = _tune("batters_eye_fastball_weight", 1.0)
BATTERS_EYE_FASTBALL_VELOCITY_BASELINE = _tune("batters_eye_fastball_velocity_baseline", 135)
BATTERS_EYE_FASTBALL_VELOCITY_SCALE = _tune("batters_eye_fastball_velocity_scale", 40)
BATTERS_EYE_BREAKER_WEIGHT = _tune("batters_eye_breaker_weight", 0.8)
BATTERS_EYE_BREAKER_MOVEMENT_BASELINE = _tune("batters_eye_breaker_movement_baseline", 60)
BATTERS_EYE_BREAKER_MOVEMENT_SCALE = _tune("batters_eye_breaker_movement_scale", 70)
BATTERS_EYE_OFFSPEED_WEIGHT = _tune("batters_eye_offspeed_weight", 0.55)
BATTERS_EYE_OFFSPEED_CONTROL_BASELINE = _tune("batters_eye_offspeed_control_baseline", 60)
BATTERS_EYE_OFFSPEED_CONTROL_SCALE = _tune("batters_eye_offspeed_control_scale", 150)

# Commentary triggers
COMMENT_CONTROL_MIN_PITCHES = _tune("comment_control_min_pitches", 12)
COMMENT_CONTROL_BALL_RATIO = _tune("comment_control_ball_ratio", 0.45)
COMMENT_CONTROL_COOLDOWN = _tune("comment_control_cooldown", 8)
COMMENT_DOM_MIN_STRIKEOUTS = _tune("comment_dom_min_strikeouts", 4)
COMMENT_DOM_INTERVAL = _tune("comment_dom_interval", 3)


class AtBatPhase(Enum):
    """High-level phases for the at-bat state machine."""

    SETUP = auto()
    RIVAL_CUTIN = auto()
    RUNNER_THREAT = auto()
    DECISION = auto()
    PITCH = auto()
    RESOLUTION = auto()
    CONTACT = auto()
    POST_PLAY = auto()


def _announce(bus, event_name: str, payload: Optional[dict] = None) -> None:
    """Publish commentary-friendly events while preserving existing prints."""

    data = payload or {}
    if bus:
        bus.publish(event_name, data)
    text = data.get("text") if isinstance(data, dict) else None
    if text and commentary_enabled():
        print(text)


def _prompt_value(state, prompt: str, default: str = "") -> str:
    """Collect user input via injected provider; fall back to default to avoid blocking."""

    provider = getattr(state, "input_provider", None)
    if callable(provider):
        try:
            return str(provider(prompt, default))
        except Exception:
            return default
    return default


def _order_label(value: str) -> str:
    return (value or "").strip().lower()


def _apply_offense_orders(order_label: str, state, batter_action: str, batter_mods: dict) -> tuple[str, dict]:
    """Blend simple approach tweaks based on standing orders for SIM pacing."""

    order = _order_label(order_label)
    if order.startswith("work"):
        batter_action = "Contact"
        batter_mods["eye_mod"] = batter_mods.get("eye_mod", 0) + 10
        batter_mods["contact_mod"] = batter_mods.get("contact_mod", 0) + 4
        batter_mods["power_mod"] = batter_mods.get("power_mod", 0) - 6
    elif order.startswith("swing") or order.startswith("attack"):
        batter_action = "Power"
        batter_mods["power_mod"] = batter_mods.get("power_mod", 0) + 10
        batter_mods["eye_mod"] = batter_mods.get("eye_mod", 0) - 8
        batter_mods["contact_mod"] = batter_mods.get("contact_mod", 0) - 2
    elif order.startswith("protect"):
        batter_action = "Contact"
        batter_mods["eye_mod"] = batter_mods.get("eye_mod", 0) + 12
        batter_mods["contact_mod"] = batter_mods.get("contact_mod", 0) + 6
        batter_mods["power_mod"] = batter_mods.get("power_mod", 0) - 8
        if getattr(state, "strikes", 0) >= 2:
            batter_mods["force_swing"] = True
    return batter_action, batter_mods


def _apply_defense_orders(order_label: str, pitcher_trait_mods: dict) -> dict:
    order = _order_label(order_label)
    if order.startswith("attack"):
        pitcher_trait_mods["control"] = pitcher_trait_mods.get("control", 0) + 3
        pitcher_trait_mods["velocity"] = pitcher_trait_mods.get("velocity", 0) + 2
    elif order.startswith("nibble") or order.startswith("pitch around"):
        pitcher_trait_mods["control"] = pitcher_trait_mods.get("control", 0) + 6
        pitcher_trait_mods["movement"] = pitcher_trait_mods.get("movement", 0) + 2
    return pitcher_trait_mods


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
    base = _tune("slide_step_base", 0.18)
    base += max(0.0, threat.lead_off_distance - 7.0) * _tune("slide_step_lead_scale", 0.04)
    base += threat.jump_quality * _tune("slide_step_jump_scale", 0.02)
    base += max(0.0, getattr(state, "pressure_index", 0.0) - 5.0) * _tune("slide_step_pressure_scale", 0.02)
    base += max(0.0, pick_skill - 55) * _tune("slide_step_pick_skill_scale", 0.002)
    base -= fatigue_level * _tune("slide_step_fatigue_penalty", 0.12)
    base = max(0.0, min(_tune("slide_step_cap", 0.8), base))
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

    slide_profile = baseline if not use_slide else evaluate_slide_step(
        pitcher,
        use_slide_step=True,
        fatigue_level=fatigue_level,
    )

    # Persist delivery timing and slide penalties for the upcoming pitch/steal logic.
    state._pending_delivery_time = slide_profile.delivery_time
    state._pending_slide_step = slide_profile
    if slide_profile.control_penalty:
        pitcher_trait_mods["control"] = pitcher_trait_mods.get("control", 0) - slide_profile.control_penalty
    if slide_profile.velocity_penalty:
        pitcher_trait_mods["velocity"] = pitcher_trait_mods.get("velocity", 0) - slide_profile.velocity_penalty
    return slide_profile


def _execute_pickoff_attempt(state, pitcher, runner_threats, target_idx: int) -> bool:
    threat = runner_threats.get(target_idx)
    if not threat:
        return False
    bus = getattr(state, "event_bus", None)
    outcome = simulate_pickoff(state, threat=threat, pitcher=pitcher)
    try:
        pid = getattr(pitcher, "id", None)
        if pid is not None:
            state.pitch_counts[pid] = state.pitch_counts.get(pid, 0) + outcome.stamina_cost
    except Exception:
        pass
    cache = getattr(state, "_cached_runner_threats", {}) or {}
    cache.pop(target_idx, None)
    pitcher_name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'Pitcher'))
    runner_name = getattr(threat.runner, 'last_name', getattr(threat.runner, 'name', 'Runner'))
    if outcome.picked_runner:
        _announce(bus, "MATCH_COMMENTARY", {
            "text": f"   >> {pitcher_name} spins and nails {runner_name}! Pickoff executed.",
            "context": "pickoff",
            "pitcher_id": getattr(pitcher, "id", None),
            "runner_id": getattr(threat.runner, "id", None),
        })
    else:
        _announce(bus, "MATCH_COMMENTARY", {
            "text": f"   >> {pitcher_name} fires over; {runner_name} dives back safely.",
            "context": "pickoff",
            "pitcher_id": getattr(pitcher, "id", None),
            "runner_id": getattr(threat.runner, "id", None),
        })
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
    base = _tune("pickoff_base", 0.08)
    base += max(0.0, threat.lead_off_distance - 7.0) * _tune("pickoff_lead_scale", 0.05)
    base += threat.jump_quality * _tune("pickoff_jump_scale", 0.03)
    base += max(0.0, pick_skill - 55) * _tune("pickoff_skill_scale", 0.003)
    base += max(0.0, getattr(state, "pressure_index", 0.0) - 6.0) * _tune("pickoff_pressure_scale", 0.015)
    base -= _pitcher_fatigue_level(state, pitcher) * _tune("pickoff_fatigue_penalty", 0.1)
    base = max(0.0, min(_tune("pickoff_cap", 0.6), base + rng.uniform(-_tune("pickoff_rng_delta", 0.02), _tune("pickoff_rng_delta", 0.02))))
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
    base_chance = SQUEEZE_BASE + max(0, getattr(state, "inning", 1) - 6) * SQUEEZE_INNING_SCALE
    if margin <= 1:
        base_chance += SQUEEZE_MARGIN_CLOSE_BONUS
    elif margin == 2:
        base_chance += SQUEEZE_MARGIN_TWO_BONUS
    pressure = getattr(state, "pressure_index", 0.0) or 0.0
    base_chance += min(0.12, pressure * SQUEEZE_PRESSURE_SCALE)
    if coach:
        volatility = getattr(coach, "volatility", 50) or 50
        drive = getattr(coach, "drive", 50) or 50
        loyalty = getattr(coach, "loyalty", 55) or 55
        base_chance += max(0, volatility - 50) * SQUEEZE_VOLATILITY_SCALE
        base_chance += max(0, drive - 55) * SQUEEZE_DRIVE_SCALE
        base_chance += max(0, 60 - loyalty) * SQUEEZE_LOYALTY_SCALE
    if player_has_skill(batter, "bunt_master"):
        base_chance += SQUEEZE_BUNT_MASTER_BONUS
    threat = (runner_threats or {}).get(2)
    if threat:
        base_chance += threat.jump_quality * SQUEEZE_JUMP_SCALE
        base_chance += max(0.0, threat.lead_off_distance - 7.0) * SQUEEZE_LEAD_SCALE
        base_chance -= max(0.0, threat.pressure) * SQUEEZE_PRESSURE_PENALTY
    if getattr(state, "defensive_shift", "normal") == "infield_in":
        base_chance -= SQUEEZE_INFIELD_IN_PENALTY
    base_chance += rng.uniform(-SQUEEZE_RNG_DELTA, SQUEEZE_RNG_DELTA)
    base_chance = max(0.0, min(SQUEEZE_MAX, base_chance))
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
        return ContactResult(HitType.OUT, "Squares early but no runner breaks.", credited_hit=False, special_play=intent.play)
    threat = (getattr(state, "_cached_runner_threats", {}) or {}).get(intent.runner_base)
    contact_skill = (getattr(batter, "contact", 50) or 50) + trait_mods.get('contact', 0)
    if player_has_skill(batter, "bunt_master"):
        contact_skill += 12
    runner_speed = getattr(runner, "speed", 50) or 50
    success = _tune("bunt_success_base", 0.45)
    success += (contact_skill - 55) * BUNT_CONTACT_SCALE
    success += (runner_speed - 60) * BUNT_SPEED_SCALE
    if threat:
        success += threat.jump_quality * BUNT_JUMP_SCALE
        success += max(0.0, threat.lead_off_distance - 7.0) * BUNT_LEAD_SCALE
    pressure = getattr(state, "pressure_index", 0.0) or 0.0
    success += min(0.12, pressure * BUNT_PRESSURE_SCALE)
    if getattr(state, "defensive_shift", "normal") == "infield_in":
        success -= BUNT_INFIELD_IN_PENALTY
    pitcher_fielding = getattr(pitcher, "fielding", getattr(pitcher, "control", 50)) or 50
    success -= max(0, pitcher_fielding - 60) * BUNT_FIELDING_PENALTY
    success = max(BUNT_MIN_SUCCESS, min(BUNT_MAX_SUCCESS, success))
    collapse = _tune("bunt_collapse_window", 0.18)
    roll = rng.random()
    if roll < success:
        moves = [(intent.runner_base, 3, runner)]
        first_runner = _runner_at_base(state, 0)
        if first_runner and getattr(state, "outs", 0) < 2:
            moves.append((0, 1, first_runner))
        hit_chance = BUNT_HIT_BASE + max(0.0, contact_skill - 60) * BUNT_HIT_CONTACT_SCALE
        if rng.random() < hit_chance:
            desc = "Drops a perfect squeeze bunt for an infield hit!"
            return ContactResult(
                HitType.SINGLE,
                desc,
                credited_hit=True,
                special_play=intent.play,
                rbi_credit=True,
            )
        desc = "Executes the squeeze! Runner slides home."
        return ContactResult(
            HitType.OUT,
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
            HitType.OUT,
            desc,
            credited_hit=False,
            runner_advances=moves,
            special_play=intent.play,
            extra_outs=1,
        )
    desc = "Can't deaden it—popup ends the squeeze."
    return ContactResult(HitType.OUT, desc, credited_hit=False, special_play=intent.play)


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


def _maybe_comment_on_control(pitcher, tracker, *, bus=None):
    if not commentary_enabled():
        return
    total = tracker.get("pitches", 0)
    if total < COMMENT_CONTROL_MIN_PITCHES:
        return
    ball_ratio = tracker.get("balls", 0) / max(1, total)
    if ball_ratio < COMMENT_CONTROL_BALL_RATIO:
        return
    if total - tracker.get("last_comment_pitch", 0) < COMMENT_CONTROL_COOLDOWN:
        return
    name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'The pitcher'))
    _announce(bus, "MATCH_COMMENTARY", {
        "text": f"   >> {name} is struggling to find the zone right now.",
        "context": "pitch_command",
        "pitcher_id": getattr(pitcher, "id", None),
    })
    tracker["last_comment_pitch"] = total


def _maybe_comment_on_dominance(pitcher, tracker, pitcher_stats, *, bus=None):
    if not commentary_enabled():
        return
    strikeouts = int(pitcher_stats.get("strikeouts_pitched", 0))
    if strikeouts < COMMENT_DOM_MIN_STRIKEOUTS or strikeouts % COMMENT_DOM_INTERVAL != 0:
        return
    if tracker.get("last_k_comment", 0) == strikeouts:
        return
    name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'The pitcher'))
    _announce(bus, "MATCH_COMMENTARY", {
        "text": f"   >> {name} already has {strikeouts} strikeouts. The hitters look lost.",
        "context": "pitch_command",
        "pitcher_id": getattr(pitcher, "id", None),
    })
    tracker["last_k_comment"] = strikeouts


def _handle_batters_eye_feedback(state, batter, pitch_res, *, bus=None):
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
    _announce(bus, "MATCH_COMMENTARY", {
        "text": f"   >> {message}",
        "context": "batters_eye",
        "batter_id": getattr(batter, "id", None),
    })
    logs = getattr(state, "logs", None)
    if isinstance(logs, list):
        logs.append(f"Batter's Eye: {message}")


def _emit_battle_math(state, batter, pitch_res, batter_action: str, *, bus=None):
    """Surface a concise clash summary so the player sees the math and intent bridge."""

    if _player_team_id(batter) != 1:
        return
    debug = getattr(pitch_res, "battle_debug", None)
    if not isinstance(debug, dict):
        return
    bat_control = debug.get("bat_control")
    hit_diff = debug.get("hit_difficulty")
    contact_mod = debug.get("contact_mod", 0)
    velo = debug.get("velocity", 0)
    breakdown = debug.get("battle_breakdown", []) or []
    delta = None
    try:
        delta = float(bat_control) - float(hit_diff)
    except Exception:
        delta = None
    short_reasons = []
    if velo:
        short_reasons.append(f"velo {velo:.0f}")
    for label, val in breakdown:
        if label in {"chase_penalty", "tunneling", "velo_bonus"} and val:
            short_reasons.append(f"{label.replace('_',' ')} {val:+.0f}")
    clash = (
        f"Clash: bat control {bat_control:.0f} vs pitch diff {hit_diff:.0f}"
        f" (intent {batter_action}, contact mod {contact_mod:+})"
    )
    if delta is not None:
        edge_label = "edge" if delta >= 0 else "deficit"
        clash += f" [{edge_label} {delta:+.0f}]"
    detail = "Drivers: " + ", ".join(short_reasons) + "." if short_reasons else ""

    # Outcome-aware bridge
    outcome = getattr(pitch_res, "outcome", "?")
    desc = getattr(pitch_res, "description", "") or outcome
    rng_note = ""
    if delta is not None:
        if delta >= 10 and outcome in {"Strike", "Foul"}:
            rng_note = "Had the advantage, but the pitch execution/paint stole it."
        elif delta <= -10 and outcome in {"InPlay", "Ball"}:
            rng_note = "Behind on paper; luck/discipline turned it in your favor."

    guess = getattr(pitch_res, "guess_payload", None) or {}
    guess_label = guess.get("label")
    guess_res = guess.get("result")
    intent_line = ""
    if guess_label:
        if guess_res == "locked_in":
            intent_line = f"You sat on {guess_label} and were ready."
        elif guess_res == "fooled":
            intent_line = f"You were hunting {guess_label}, but got something else."

    lines = [clash]
    if detail:
        lines.append(detail)
    if intent_line:
        lines.append(intent_line)
    if rng_note:
        lines.append(rng_note)
    lines.append(f"Result: {outcome} — {desc}")

    msg = " " .join(lines)
    _announce(bus, "MATCH_COMMENTARY", {
        "text": f"   >> {msg}",
        "context": "battle_math",
        "batter_id": getattr(batter, "id", None),
    })
    logs = getattr(state, "logs", None)
    if isinstance(logs, list):
        logs.append(msg)


def _emit_pitch_grid(state, batter, pitch_res, *, bus=None):
    """Log/print a quick pitch map for user batters to show in/out location."""

    if _player_team_id(batter) != 1:
        return
    location = getattr(pitch_res, "location", None)
    if not location:
        return
    highlight = 5 if getattr(pitch_res, "in_zone", location == "Zone") else "O11"
    lines = build_pitch_snapshot_lines(location, highlight_zone=highlight, heat_stats={}, theme_name="persona", color=False)

    pitch_name = getattr(pitch_res, "pitch_name", "?")
    family = getattr(pitch_res, "pitch_family", "")
    arm_slot = getattr(pitch_res, "arm_slot", "")
    slot_group = getattr(pitch_res, "slot_group", "")
    velocity = getattr(pitch_res, "velocity", 0)
    zone_label = getattr(pitch_res, "zone_label", "")
    header = f"Pitch Map: {pitch_name} ({velocity:.0f} mph) [{zone_label}]"
    meta_bits = []
    if family:
        meta_bits.append(f"family: {family}")
    if arm_slot:
        meta_bits.append(f"arm slot: {arm_slot}")
    if slot_group:
        meta_bits.append(f"slot group: {slot_group}")
    if meta_bits:
        header += " | " + "; ".join(meta_bits)

    block = "\n".join([header] + lines)
    _announce(bus, "MATCH_COMMENTARY", {
        "text": block,
        "context": "pitch_grid",
        "batter_id": getattr(batter, "id", None),
    })
    logs = getattr(state, "logs", None)
    if isinstance(logs, list):
        logs.append(block)


def _auto_batters_eye_guess(state, batter, pitcher, tendencies=None):
    if not state or not batter or not pitcher:
        return None
    discipline = getattr(batter, "discipline", 50) or 50
    mental = getattr(batter, "mental", 50) or 50
    clutch = getattr(batter, "clutch", 50) or 50
    base = BATTERS_EYE_BASE
    base += max(0, discipline - 50) * BATTERS_EYE_DISCIPLINE_SCALE
    base += max(0, mental - 50) * BATTERS_EYE_MENTAL_SCALE
    base += max(0, clutch - 60) * BATTERS_EYE_CLUTCH_SCALE
    if player_has_skill(batter, "contact_artist"):
        base += BATTERS_EYE_CONTACT_ARTIST_BONUS
    if player_has_skill(batter, "walk_machine"):
        base += BATTERS_EYE_WALK_MACHINE_BONUS
    if player_has_skill(batter, "tough_out"):
        base += BATTERS_EYE_TOUGH_OUT_BONUS
    tendencies = tendencies or {}
    aggression = tendencies.get("swing_aggression", 1.0)
    if aggression > BATTERS_EYE_AGGRESSION_THRESHOLD:
        base -= min(BATTERS_EYE_AGGRESSION_PENALTY_CAP, (aggression - BATTERS_EYE_AGGRESSION_THRESHOLD) * BATTERS_EYE_AGGRESSION_PENALTY_SCALE)
    base = max(BATTERS_EYE_MIN, min(BATTERS_EYE_MAX, base))
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
    if balls - strikes >= BATTERS_EYE_ZONE_COUNT_DIFF or (balls >= BATTERS_EYE_ZONE_FRIENDLY_BALLS and strikes <= BATTERS_EYE_ZONE_FRIENDLY_STRIKES):
        zone_weight = BATTERS_EYE_ZONE_WEIGHT
    if pressure >= BATTERS_EYE_ZONE_PRESSURE_THRESHOLD:
        zone_weight += BATTERS_EYE_ZONE_PRESSURE_BONUS
    _add_option("location", "zone", "Challenge Strike", zone_weight, "green light count")

    chase_weight = 0.0
    if strikes >= BATTERS_EYE_CHASE_PROTECT_STRIKES and balls <= BATTERS_EYE_CHASE_PROTECT_BALLS:
        chase_weight = BATTERS_EYE_CHASE_WEIGHT
    _add_option("location", "chase", "Waste Pitch", chase_weight, "protect mode")

    fastball_weight = BATTERS_EYE_FASTBALL_WEIGHT + max(0, velocity - BATTERS_EYE_FASTBALL_VELOCITY_BASELINE) / BATTERS_EYE_FASTBALL_VELOCITY_SCALE
    _add_option("family", "fastball", "Fastball", fastball_weight, "respecting heat")

    breaker_weight = BATTERS_EYE_BREAKER_WEIGHT + max(0, movement - BATTERS_EYE_BREAKER_MOVEMENT_BASELINE) / BATTERS_EYE_BREAKER_MOVEMENT_SCALE
    _add_option("family", "breaker", "Breaking Ball", breaker_weight, "expecting spin")

    offspeed_weight = BATTERS_EYE_OFFSPEED_WEIGHT + max(0, control - BATTERS_EYE_OFFSPEED_CONTROL_BASELINE) / BATTERS_EYE_OFFSPEED_CONTROL_SCALE
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
    bus = getattr(state, "event_bus", None)
    pinch_name = getattr(pinch, 'last_name', getattr(pinch, 'name', 'Batter'))
    prev_name = getattr(previous, 'last_name', getattr(previous, 'name', 'starter'))
    team_label = getattr(offense_team, 'name', 'Coach')
    _announce(bus, "MATCH_COMMENTARY", {
        "text": f"   >> {team_label} summons {pinch_name} (Gap-to-Gap milestone) to hit for {prev_name}.",
        "context": "pinch_hit",
        "team_id": team_id,
        "batter_id": getattr(pinch, "id", None),
        "replaced_id": getattr(previous, "id", None),
    })
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

    base_chance = STEAL_BASE
    base_chance += max(0, volatility - 50) * STEAL_VOLATILITY_SCALE
    base_chance += max(0, drive - 55) * STEAL_DRIVE_SCALE
    base_chance -= max(0, 55 - loyalty) * STEAL_LOYALTY_SCALE
    runner_speed = getattr(runner, 'speed', 50) or 50
    base_chance += max(0, runner_speed - 65) * STEAL_SPEED_SCALE

    threat_map = runner_threats or getattr(state, "_cached_runner_threats", {}) or {}
    threat = threat_map.get(0)
    if threat:
        lead_bonus = (threat.lead_off_distance - 7.0) * STEAL_LEAD_SCALE
        jump_bonus = threat.jump_quality * STEAL_JUMP_SCALE
        pressure_penalty = threat.pressure * STEAL_PRESSURE_PENALTY
        base_chance += lead_bonus + jump_bonus - pressure_penalty
    if player_has_skill(runner, "speed_demon"):
        base_chance += _tune("steal_speed_demon_bonus", 0.025)

    pickoff_rating = getattr(opp_pitcher, 'pickoff_rating', None)
    if pickoff_rating is None:
        pickoff_rating = getattr(opp_pitcher, 'control', 50) or 50
    base_chance -= max(0, pickoff_rating - 60) * STEAL_PICKOFF_PENALTY
    base_chance += rng.uniform(-STEAL_RNG_DELTA, STEAL_RNG_DELTA)

    bus = getattr(state, "event_bus", None)
    if _player_has_milestone(state, runner, "walkoff_spark"):
        base_chance += STEAL_WALKOFF_BONUS
        runner_name = getattr(runner, 'last_name', getattr(runner, 'name', 'Runner'))
        _announce(bus, "MATCH_COMMENTARY", {
            "text": f"   >> Milestone swagger: {runner_name} earned Walk-off Spark; coach trusts his jump.",
            "context": "steal_call",
            "runner_id": getattr(runner, "id", None),
        })

    # Late innings or when trailing nudges aggression upward
    offense_is_away = state.top_bottom == "Top"
    score_diff = (state.away_score - state.home_score) if offense_is_away else (state.home_score - state.away_score)
    if state.inning >= 7 and abs(score_diff) <= 2:
        base_chance += STEAL_LATE_INNING_BONUS
    if score_diff < 0:
        base_chance += STEAL_TRAILING_BONUS

    base_chance = max(0.0, min(STEAL_MAX, base_chance))
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
    coach_name = getattr(coach, 'name', 'Coach')
    runner_name = getattr(runner, 'last_name', getattr(runner, 'name', 'Runner'))
    _announce(bus, "MATCH_COMMENTARY", {
        "text": f"   >> {coach_name} flashes the steal sign for {runner_name}!",
        "context": "steal_call",
        "runner_id": getattr(runner, "id", None),
    })
    _announce(bus, "MATCH_COMMENTARY", {
        "text": f"   >> {message}",
        "context": "steal_result",
        "runner_id": getattr(runner, "id", None),
    })

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
    io = getattr(state, "io", None)
    if _catcher_trusts_shift(state):
        new_shift = prompt_defensive_shift(current, io=io)
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
    hit_type = contact_res.hit_type
    if isinstance(hit_type, str) and hit_type in HitType._value2member_map_:
        hit_type = HitType(hit_type)
    if hit_type == HitType.OUT:
        adjust_confidence(state, getattr(batter, 'id', None), -4, reason="out")
        adjust_confidence(state, getattr(pitcher, 'id', None), 3, reason="heroics")
        return
    boosts = {HitType.SINGLE: 5, HitType.DOUBLE: 7, HitType.TRIPLE: 9, HitType.HOMERUN: 12}
    base = boosts.get(hit_type, 4)
    if not contact_res.credited_hit:
        base = max(2, base - 3)
    adjust_confidence(state, getattr(batter, 'id', None), base, reason="clutch_hit")
    adjust_confidence(state, getattr(pitcher, 'id', None), -min(base, 8), reason="hit_allowed")


def _broadcast_confidence_flashes(state, *, bus=None):
    events = collect_confidence_flashes(state)
    if not commentary_enabled():
        return
    for event in events:
        direction = "surging" if event["delta"] > 0 else "reeling"
        magnitude = f"{event['delta']:+.0f}"
        reason = event.get("reason") or "moment"
        inning = event.get("inning") or getattr(state, "inning", 0)
        _announce(bus, "MATCH_COMMENTARY", {
            "text": f"   >> Confidence pulse ({inning}): {event['name']} is {direction} ({magnitude}, {reason}).",
            "context": "confidence",
            "player_id": event.get("player_id"),
        })


def _handle_argument_event(state, pitch_res, batter, pitcher):
    label = getattr(pitch_res, 'special', None)
    if label not in {"argument_batter", "argument_pitcher"}:
        return
    penalty = getattr(pitch_res, 'argument_penalty', 0) or 0
    target = batter if label == "argument_batter" else pitcher
    target_id = getattr(target, 'id', None)
    ejected = getattr(pitch_res, 'argument_ejection', False)
    bus = getattr(state, "event_bus", None)
    if penalty > 0:
        adjust_confidence(state, target_id, -penalty, reason="ump_argument", contagious=False)
        morale = getattr(target, 'morale', 60) or 60
        morale -= max(1, penalty // 2)
        target.morale = max(15, morale)
        name = getattr(target, 'last_name', getattr(target, 'name', 'Player'))
        _announce(bus, "MATCH_COMMENTARY", {
            "text": f"   >> {name} barks at the ump and gets rattled ({penalty} confidence hit).",
            "context": "argument",
            "player_id": target_id,
        })
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
    bus = getattr(state, "event_bus", None)
    if commentary_enabled():
        name = getattr(player, 'last_name', getattr(player, 'name', 'Player'))
        _announce(bus, "MATCH_COMMENTARY", {
            "text": f"   >> {name} is tossed after the argument! Umpire patience ran out.",
            "context": "argument",
            "player_id": pid,
        })


def _prompt_swing_choice(state, pitcher, batter):
    """Lightweight swing selector for manual debug flow."""
    if getattr(state, "auto_play_inputs", False):
        return "Swing", {"contact_mod": 0, "power_mod": 0, "eye_mod": 0}
    balls = getattr(state, "balls", 0)
    strikes = getattr(state, "strikes", 0)
    outs = getattr(state, "outs", 0)
    print("\n[Swing Choice] Pick your approach")
    print(f" Count {balls}-{strikes} | Outs {outs}")
    print(" 1. Normal swing (balanced)")
    print(" 2. Contact swing (safer, less pop)")
    print(" 3. Power swing (risk/reward)")
    print(" 4. Take pitch (no swing)")

    default_action = "Swing"
    default_mods = {"contact_mod": 0, "power_mod": 0, "eye_mod": 0}
    choice = _prompt_value(state, " Swing #: ", default="1").strip()

    if choice == "2":
        action = "Contact"
        mods = {"contact_mod": 20, "power_mod": -30, "eye_mod": 10}
    elif choice == "3":
        action = "Power"
        mods = {"contact_mod": -20, "power_mod": 25, "eye_mod": -10}
    elif choice == "4":
        action = "Take"
        mods = {}
    else:
        action = default_action
        mods = default_mods

    try:
        from player_roles.batter_controls import _prompt_batters_eye
        guess_payload = _prompt_batters_eye()
        if guess_payload:
            mods["guess_payload"] = guess_payload
    except Exception:
        pass
    return action, mods


def _maybe_prompt_manual_pitch(state, pitcher, batter):
    if getattr(state, "auto_play_inputs", False):
        return
    team_ids = getattr(state, "human_team_ids", set()) or set()
    if not team_ids:
        return
    pitcher_team = getattr(pitcher, "team_id", getattr(pitcher, "school_id", None))
    if pitcher_team not in team_ids:
        return
    try:
        from match_engine.pitch_logic import get_arsenal
        arsenal = get_arsenal(getattr(pitcher, "id", None)) or []
    except Exception:
        arsenal = []

    options = []
    for idx, pitch in enumerate(arsenal, start=1):
        name = getattr(pitch, "pitch_name", "Pitch")
        desc = (PITCH_TYPES.get(name) or {}).get("desc", "")
        options.append((idx, name, desc))

    if not options:
        return

    print("\n[Pitch Call] Choose pitch and location")
    for idx, name, desc in options:
        print(f"  {idx}. {name} - {desc}")
    try:
        sel_raw = _prompt_value(state, " Pitch #: ", default="1").strip()
        sel_idx = int(sel_raw) if sel_raw else 1
    except ValueError:
        sel_idx = 1
    sel_idx = max(1, min(sel_idx, len(options)))
    pitch_name = options[sel_idx - 1][1]

    loc_map = {
        "1": "Up-In",
        "2": "Up",
        "3": "Up-Out",
        "4": "Mid-In",
        "5": "Zone",
        "6": "Mid-Out",
        "7": "Down-In",
        "8": "Down",
        "9": "Down-Out",
    }
    print("  Location grid (1-9 like numpad):")
    print("   7 8 9  (Up-In / Up / Up-Out)")
    print("   4 5 6  (Mid-In / Zone / Mid-Out)")
    print("   1 2 3  (Down-In / Down / Down-Out)")
    loc_choice = _prompt_value(state, " Location #: ", default="5").strip()
    location = loc_map.get(loc_choice, "Zone")

    # Build manual call wrapper expected by resolve_pitch override
    class _ManualCall:
        def __init__(self, pitch_name, location):
            self.pitch = type("_P", (), {"pitch_name": pitch_name, "break_level": getattr(pitcher, "breaking_ball", 50) or 50})()
            self.location = location
            self.intent = "Manual"
            self.shakes = 0
            self.trust = 80
            self.forced = True

    state.manual_pitch_call = {
        "pitcher_id": getattr(pitcher, "id", None),
        "call": _ManualCall(pitch_name, location),
    }

class AtBatStateMachine:
    STATE_WINDUP = "STATE_WINDUP"
    STATE_PITCH_FLIGHT = "STATE_PITCH_FLIGHT"
    STATE_CONTACT = "STATE_CONTACT"
    STATE_RESOLVE = "STATE_RESOLVE"

    def __init__(self, state, input_source=None):
        self.state = state
        self.bus = getattr(state, "event_bus", None)
        self.input_source = input_source
        self.pitcher = None
        self.batter = None
        self.lineup = None
        self.batting_team = None
        self.batter_id = None
        self.pitcher_id = None
        self.offense_team_id = None
        self.batter_stats = None
        self.pitcher_stats = None
        self.batter_tendencies = None
        self.times_faced = 0
        self.sim_fast = False
        self.offense_order = None
        self.defense_order = None
        self.pressure_updater = None
        self.steal_checked = False
        self.squeeze_called = False
        self.last_pitch_res = None
        self.rival_ctx = None
        self.rival_intro_done = False
        self.rival_batter_mods: dict = {}
        self.rival_pitcher_mods: dict = {}

    def _emit_state(self, state_name: str, payload: Optional[dict[str, object]] = None) -> None:
        if self.bus:
            data = payload or {}
            data.setdefault("state", state_name)
            self.bus.publish("MATCH_STATE_CHANGE", data)

    def _emit_phase(self, phase: AtBatPhase, payload: Optional[dict[str, object]] = None) -> None:
        if not self.bus:
            return
        data = payload or {}
        data.setdefault("phase", phase.name)
        self.bus.publish("ATBAT_PHASE", data)

    def _phase_setup(self) -> None:
        state = self.state
        self.pitcher = state.home_pitcher if state.top_bottom == "Top" else state.away_pitcher
        self.lineup = state.away_lineup if state.top_bottom == "Top" else state.home_lineup
        self.batter = self.lineup[0]
        self.batter = _maybe_call_milestone_pinch_hit(state, self.lineup)
        self.lineup[0] = self.batter
        self.batting_team = state.away_team if state.top_bottom == "Top" else state.home_team
        self.offense_team_id = _offense_team_id(state)
        self.batter_id = getattr(self.batter, 'id', None)
        self.pitcher_id = getattr(self.pitcher, 'id', None)

        self.pressure_updater = getattr(state, "update_pressure_index", None)
        if callable(self.pressure_updater):
            self.pressure_updater()

        state.reset_count()
        state.defensive_shift = "normal"
        _reset_plate_summary(state)
        self.batter_stats = state.get_stats(self.batter.id)
        self.pitcher_stats = state.get_stats(self.pitcher.id)
        state.latest_play_detail = None
        if commentary_enabled():
            display_state(state, self.pitcher, self.batter)

        self.batter_tendencies = gather_behavior_tendencies(self.batter)
        self.times_faced = state.register_plate_appearance(self.pitcher_id, self.batter_id)
        play_mode_value = getattr(state, "play_mode", PlayMode.SIM.value)
        self.sim_fast = str(play_mode_value).upper() == PlayMode.SIM.value
        orders = getattr(state, "standing_orders", {}) or {}
        self.offense_order = orders.get("offense")
        self.defense_order = orders.get("defense")
        if self.sim_fast:
            state.fast_sim = True
        self.steal_checked = False
        self.squeeze_called = False
        self.rival_ctx = getattr(state, "rival_match_context", None) or getattr(state, "rival_context", None)
        self._emit_phase(AtBatPhase.SETUP, {
            "inning": state.inning,
            "half": state.top_bottom,
            "batter_id": self.batter_id,
            "pitcher_id": self.pitcher_id,
        })

    def _phase_rival_cutin(self) -> None:
        """Trigger the rivalry cut-in before the at-bat begins."""

        state = self.state
        if self.rival_intro_done or not self.rival_ctx:
            return

        is_rival_plate = self.rival_ctx.is_rival_plate(self.batter_id)
        if not is_rival_plate:
            return

        self._emit_phase(AtBatPhase.RIVAL_CUTIN, {
            "inning": state.inning,
            "half": state.top_bottom,
            "batter_id": self.batter_id,
            "pitcher_id": self.pitcher_id,
        })

        if state.balls == 0 and state.strikes == 0:
            rival_name = getattr(self.batter, "last_name", getattr(self.batter, "name", "Rival"))
            hero_name = getattr(self.pitcher, "last_name", getattr(self.pitcher, "name", "Pitcher"))
            _announce(self.bus, "MATCH_COMMENTARY", {
                "text": f"   >> The air grows heavy. {hero_name} locks eyes with {rival_name}!",
                "context": "rival_cutin",
                "batter_id": self.batter_id,
                "pitcher_id": self.pitcher_id,
            })
            heat = getattr(getattr(self.rival_ctx, "rival", None), "heat_level", 0)
            if heat > 50:
                self.rival_batter_mods["contact_mod"] = self.rival_batter_mods.get("contact_mod", 0) + 5
                self.rival_pitcher_mods["velocity_mod"] = self.rival_pitcher_mods.get("velocity_mod", 0) + 3
                _announce(self.bus, "MATCH_COMMENTARY", {
                    "text": "      Rivalry heat surges! Both players rise to the moment.",
                    "context": "rival_heat",
                    "batter_id": self.batter_id,
                    "pitcher_id": self.pitcher_id,
                })

        self.rival_intro_done = True

    def _phase_batter_decision(self) -> tuple[str, dict]:
        state = self.state
        batter_action = "Normal"
        batter_mods: dict = {}
        human_team_ids = getattr(state, "human_team_ids", set()) or set()
        user_controls = (_player_team_id(self.batter) in human_team_ids) and not self.sim_fast
        io = getattr(state, "io", None)

        if getattr(state, "manual_pitch_calls", False):
            _maybe_prompt_manual_pitch(state, self.pitcher, self.batter)

        self._emit_phase(AtBatPhase.DECISION, {
            "inning": state.inning,
            "half": state.top_bottom,
            "batter_id": self.batter_id,
            "pitcher_id": self.pitcher_id,
        })

        if user_controls and getattr(state, "manual_swing_prompts", False):
            batter_action, batter_mods = _prompt_swing_choice(state, self.pitcher, self.batter)
        elif self.input_source is not None:
            batter_action, batter_mods = self.input_source.get_batting_decision({
                "pitcher": self.pitcher,
                "batter": self.batter,
                "state": state,
                "offense_order": self.offense_order,
                "batter_tendencies": self.batter_tendencies,
            })
        elif user_controls:
            from player_roles.batter_controls import player_bat_turn
            batter_action, batter_mods = player_bat_turn(self.pitcher, self.batter, state, io=io)
        else:
            batter_action, batter_mods = _apply_offense_orders(self.offense_order, state, batter_action, batter_mods)
            guess_payload = _auto_batters_eye_guess(state, self.batter, self.pitcher, self.batter_tendencies)
            if guess_payload:
                batter_mods['guess_payload'] = guess_payload
        if self.rival_batter_mods:
            for key, delta in self.rival_batter_mods.items():
                batter_mods[key] = batter_mods.get(key, 0) + delta
        return batter_action, batter_mods

    def _phase_runner_threats(self, batter_action: str, batter_mods: dict) -> tuple[str, dict, dict]:
        state = self.state
        state._pending_delivery_time = None
        state._pending_slide_step = None
        slide_trait_mods: dict = {}

        defense_runners = getattr(state, "runners", None) or []
        if _user_controls_defense(state) and any(defense_runners[:2]):
            from player_roles.pitcher_controls import prompt_runner_threat_controls
            prompt_runner_threat_controls(self.pitcher, state, io=io)

        self._emit_phase(AtBatPhase.RUNNER_THREAT, {
            "inning": state.inning,
            "half": state.top_bottom,
            "batter_id": self.batter_id,
            "pitcher_id": self.pitcher_id,
        })

        runner_threats = _capture_runner_threats(state)
        slide_profile = None
        if runner_threats:
            if _handle_manual_pickoff_request(state, self.pitcher, runner_threats):
                if state.outs >= 3:
                    return "end", batter_mods, runner_threats
                return "restart", batter_mods, runner_threats
            slide_profile = _apply_slide_step_modifiers(state, self.pitcher, slide_trait_mods, runner_threats)
            if _maybe_call_pickoff_attempt(state, self.pitcher, runner_threats):
                if state.outs >= 3:
                    return "end", batter_mods, runner_threats
                return "restart", batter_mods, runner_threats
        else:
            state._pending_delivery_time = None

        squeeze_intent = None
        if not self.squeeze_called and _player_team_id(self.batter) != 1:
            squeeze_intent = _maybe_call_squeeze_play(state, self.batter, runner_threats)
            if squeeze_intent:
                self.squeeze_called = True
                batter_action = "Bunt"
                _apply_squeeze_mods(batter_mods, squeeze_intent)
                if self.bus:
                    self.bus.publish(
                        EventType.OFFENSE_CALLS_SQUEEZE.value,
                        {
                            "inning": state.inning,
                            "half": state.top_bottom,
                            "batter_id": self.batter_id,
                            "runner_id": getattr(_runner_at_base(state, squeeze_intent.runner_base), "id", None),
                            "team_id": getattr(self.batting_team, 'id', None),
                        },
                    )
                _announce(self.bus, "MATCH_COMMENTARY", {
                    "text": f"   >> {getattr(self.batting_team, 'name', 'Coach')} flashes the squeeze! Runner breaks for home.",
                    "context": "squeeze",
                    "team_id": getattr(self.batting_team, 'id', None),
                })

        if not self.steal_checked:
            steal_result = _maybe_call_aggressive_play(state, runner_threats)
            self.steal_checked = True
            if steal_result == "runner_out":
                if state.outs >= 3:
                    return "end", batter_mods, runner_threats
                return "restart", batter_mods, runner_threats

        return "proceed", batter_mods, slide_trait_mods

    def _phase_prepare_traits(self, batter_mods: dict, slide_trait_mods: dict) -> tuple[dict, dict]:
        state = self.state
        trait_context = get_at_bat_context(state, self.batter, self.pitcher)
        batter_trait_mods = _collect_trait_mods(self.batter, trait_context)
        pitcher_trait_mods = _collect_trait_mods(self.pitcher, trait_context)
        if slide_trait_mods:
            for key, delta in slide_trait_mods.items():
                pitcher_trait_mods[key] = pitcher_trait_mods.get(key, 0) + delta
        if self.rival_pitcher_mods:
            for key, delta in self.rival_pitcher_mods.items():
                pitcher_trait_mods[key] = pitcher_trait_mods.get(key, 0) + delta
        if self.sim_fast:
            _apply_defense_orders(self.defense_order, pitcher_trait_mods)

        _configure_defensive_shift(state)
        return batter_trait_mods, pitcher_trait_mods

    def _phase_pitch(self, batter_action: str, batter_mods: dict, batter_trait_mods: dict, pitcher_trait_mods: dict):
        state = self.state
        self._emit_state(self.STATE_PITCH_FLIGHT, {
            "inning": state.inning,
            "half": state.top_bottom,
            "balls": state.balls,
            "strikes": state.strikes,
        })
        self._emit_phase(AtBatPhase.PITCH, {
            "inning": state.inning,
            "half": state.top_bottom,
            "batter_id": self.batter_id,
            "pitcher_id": self.pitcher_id,
        })
        state.add_pitch_count(self.pitcher.id)
        pitch_res = resolve_pitch(
            self.pitcher,
            self.batter,
            state,
            batter_action,
            batter_mods,
            batter_trait_mods=batter_trait_mods,
            pitcher_trait_mods=pitcher_trait_mods,
            batter_tendencies=self.batter_tendencies,
            times_through_order=self.times_faced,
        )
        self.last_pitch_res = pitch_res
        state.last_pitch_snapshot = {
            "velocity": getattr(pitch_res, "velocity", 0),
            "pitch_name": getattr(pitch_res, "pitch_name", None),
            "pitch_family": getattr(pitch_res, "pitch_family", None),
            "location": getattr(pitch_res, "location", None),
            "result": getattr(pitch_res, "outcome", None),
            "contact_quality": getattr(pitch_res, "contact_quality", None),
        }
        tracker = _update_pitch_diagnostics(state, self.pitcher.id, pitch_res.outcome)

        announce_pitch(pitch_res)
        _maybe_comment_on_control(self.pitcher, tracker, bus=self.bus)
        _handle_argument_event(state, pitch_res, self.batter, self.pitcher)
        _handle_batters_eye_feedback(state, self.batter, pitch_res, bus=self.bus)
        _emit_battle_math(state, self.batter, pitch_res, batter_action, bus=self.bus)
        _emit_pitch_grid(state, self.batter, pitch_res, bus=self.bus)
        return pitch_res, tracker

    def _phase_contact(self, pitch_res, batter_trait_mods: dict, bases_loaded_snapshot: bool, outs_snapshot: int) -> None:
        state = self.state
        self._emit_state(self.STATE_CONTACT, {
            "inning": state.inning,
            "half": state.top_bottom,
            "quality": pitch_res.contact_quality,
        })
        self._emit_phase(AtBatPhase.CONTACT, {
            "inning": state.inning,
            "half": state.top_bottom,
            "batter_id": self.batter_id,
            "pitcher_id": self.pitcher_id,
            "quality": getattr(pitch_res, "contact_quality", None),
        })
        p_mod = getattr(pitch_res, 'power_mod', 0)
        bunt_intent = getattr(pitch_res, "bunt_intent", None)
        if bunt_intent and getattr(bunt_intent, "squeeze", False):
            contact_res = _resolve_bunt_contact(state, self.batter, self.pitcher, bunt_intent, batter_trait_mods)
        else:
            contact_res = resolve_contact(
                pitch_res.contact_quality,
                self.batter,
                self.pitcher,
                state,
                power_mod=p_mod,
                trait_mods=batter_trait_mods,
            )
        announce_play(contact_res)
        hit_type = contact_res.hit_type
        if isinstance(hit_type, str) and hit_type in HitType._value2member_map_:
            hit_type = HitType(hit_type)
            contact_res.hit_type = hit_type
        reached_base = hit_type != HitType.OUT
        was_slumping = reached_base and get_confidence(state, self.batter_id) <= -30
        _apply_contact_confidence(state, self.batter, self.pitcher, contact_res)
        error_flag = bool(getattr(contact_res, "error_on_play", False))

        snap = getattr(state, "last_pitch_snapshot", {}) or {}
        snap.update(
            {
                "exit_velocity": getattr(contact_res, "exit_velocity", None),
                "launch_angle": getattr(contact_res, "launch_angle", None),
                "distance": getattr(contact_res, "distance", None),
                "result": "inplay",
                "hit_type": getattr(contact_res, "hit_type", None),
            }
        )
        state.last_pitch_snapshot = snap

        if hit_type != HitType.OUT and getattr(self.batter, "position", "").lower() == "pitcher":
            _trigger_presence(state, self.pitcher, "hit_allowed_to_pitcher", "Pitcher Hit Allowed")
        if hit_type != HitType.OUT and _is_cleanup(self.batter) and hit_type in {HitType.DOUBLE, HitType.TRIPLE, HitType.HOMERUN}:
            _trigger_presence(state, self.batter, "extra_base_hit", "Cleanup Slug")

        runs_scored_on_play = 0
        if hit_type == HitType.OUT:
            outs_recorded = 1 + int(getattr(contact_res, "extra_outs", 0))
            state.outs += outs_recorded
            if not getattr(contact_res, "sacrifice", False):
                self.batter_stats["at_bats"] += 1
            self.pitcher_stats["innings_pitched"] += 0.33 * outs_recorded
            reset_slump_chain(state, self.batter_id)
            record_pitcher_stress(state, self.pitcher_id, spike=False)
            reset_rally_tracker(state, self.offense_team_id)
        else:
            self.batter_stats["at_bats"] += 1
            if contact_res.credited_hit:
                self.batter_stats["hits"] += 1
            if hit_type == HitType.HOMERUN and contact_res.credited_hit:
                self.batter_stats["homeruns"] += 1

            pre_home = state.home_score
            pre_away = state.away_score
            runs = advance_runners(state, hit_type, self.batter)
            lead_change = _lead_changed(state, runs, pre_home, pre_away)
            runs_scored_on_play = runs

            if runs > 0:
                announce_score_change(runs, getattr(self.batting_team, 'name', 'Unknown School'))
                if state.top_bottom == "Top":
                    state.away_score += runs
                else:
                    state.home_score += runs

                if contact_res.credited_hit:
                    self.batter_stats["rbi"] += runs
                self.pitcher_stats["runs_allowed"] += runs
                if lead_change:
                    apply_lead_change_swing(state)
            if runs > 0 and _is_cleanup(self.batter):
                _trigger_presence(state, self.batter, "rbi", "Cleanup RBI")

            record_pitcher_stress(state, self.pitcher_id, spike=True)
            record_rally_progress(state, self.offense_team_id, self.batter_id, reached_base=True)
            apply_slump_boost(state, self.batter_id, was_slumping, "hit")
            maybe_catcher_settle(state, self.pitcher_id)

        advances = getattr(contact_res, "runner_advances", None)
        if advances:
            pre_home_adv = state.home_score
            pre_away_adv = state.away_score
            extra_runs = _apply_runner_advancements(state, advances)
            if extra_runs:
                runs_scored_on_play += extra_runs
                announce_score_change(extra_runs, getattr(self.batting_team, 'name', 'Unknown School'))
                if state.top_bottom == "Top":
                    state.away_score += extra_runs
                else:
                    state.home_score += extra_runs
                if getattr(contact_res, "rbi_credit", False):
                    self.batter_stats["rbi"] += extra_runs
                self.pitcher_stats["runs_allowed"] += extra_runs
                if _lead_changed(state, extra_runs, pre_home_adv, pre_away_adv):
                    apply_lead_change_swing(state)

        outs_logged = max(0, state.outs - outs_snapshot)
        state.latest_play_detail = {
            "hit_type": contact_res.hit_type,
            "outs_on_play": outs_logged,
            "double_play": outs_logged >= 2 and contact_res.hit_type == HitType.OUT,
            "runs_scored": runs_scored_on_play,
            "description": contact_res.description,
            "credited_hit": contact_res.credited_hit,
            "error_on_play": error_flag,
            "error_type": getattr(contact_res, "error_type", None),
            "error_position": getattr(contact_res, "primary_position", None),
        }

    def _phase_resolution(self, pitch_res, bases_loaded_snapshot: bool, outs_snapshot: int, tracker, batter_trait_mods: dict) -> str:
        state = self.state
        self._emit_state(self.STATE_RESOLVE, {
            "outcome": pitch_res.outcome,
            "inning": state.inning,
            "half": state.top_bottom,
        })
        self._emit_phase(AtBatPhase.RESOLUTION, {
            "outcome": pitch_res.outcome,
            "inning": state.inning,
            "half": state.top_bottom,
        })

        if pitch_res.outcome == "Ball":
            state.balls += 1
            special = getattr(pitch_res, 'special', None)
            if special in {"wild_pitch", "passed_ball"}:
                label = "Wild pitch" if special == "wild_pitch" else "Passed ball"
                _announce(self.bus, "MATCH_COMMENTARY", {
                    "text": f"   >> {label}! Everyone moves up 90 feet.",
                    "context": "wild_pitch" if special == "wild_pitch" else "passed_ball",
                })
                call_ctx = getattr(state, "last_battery_call", {}) or {}
                trust_note = call_ctx.get("trust")
                wall_note = call_ctx.get("wall")
                archetype = call_ctx.get("label")
                detail_bits = []
                if archetype:
                    detail_bits.append(archetype)
                if wall_note is not None:
                    detail_bits.append(f"Wall {wall_note:.0f}")
                if trust_note is not None:
                    detail_bits.append(f"Trust {float(trust_note):.0f}")
                if detail_bits:
                    status = "Cross-up vibes" if trust_note is not None and float(trust_note) < 45 else "Battery note"
                    _announce(self.bus, "MATCH_COMMENTARY", {
                        "text": f"      {status}: {' | '.join(detail_bits)}",
                        "context": "wild_pitch_detail",
                    })
                wild_runs = _advance_on_wild_pitch(state)
                if wild_runs:
                    announce_score_change(wild_runs, getattr(self.batting_team, 'name', 'Unknown School'))
                    if state.top_bottom == "Top":
                        state.away_score += wild_runs
                    else:
                        state.home_score += wild_runs
                    self.pitcher_stats["runs_allowed"] += wild_runs
                pitcher_hit = -6 if special == "wild_pitch" else -2
                catcher_hit = -3 if special == "wild_pitch" else -6
                adjust_confidence(state, getattr(self.pitcher, 'id', None), pitcher_hit, reason="wild_pitch")
                catcher = get_current_catcher(state)
                if catcher:
                    adjust_confidence(state, getattr(catcher, 'id', None), catcher_hit, reason="wild_pitch", contagious=False)
                    adjust_battery_sync(state, self.pitcher_id, getattr(catcher, 'id', None), -0.45 if special == "wild_pitch" else -0.25)
                record_pitcher_stress(state, self.pitcher_id, spike=(special == "wild_pitch"))
                maybe_catcher_settle(state, self.pitcher_id)
            elif special == "blocked_pitch":
                call_ctx = getattr(state, "last_battery_call", {}) or {}
                wall_note = call_ctx.get("wall")
                trust_note = call_ctx.get("trust")
                archetype = call_ctx.get("label")
                detail_bits = []
                if archetype:
                    detail_bits.append(archetype)
                if wall_note is not None:
                    detail_bits.append(f"Wall {wall_note:.0f}")
                if trust_note is not None:
                    detail_bits.append(f"Trust {float(trust_note):.0f}")
                detail = f" ({' | '.join(detail_bits)})" if detail_bits else ""
                _announce(self.bus, "MATCH_COMMENTARY", {
                    "text": f"   >> Blocked in the dirt. Runners hold.{detail}",
                    "context": "blocked_pitch",
                })
                snap = getattr(state, "last_pitch_snapshot", {}) or {}
                snap["result"] = "blocked_pitch"
                state.last_pitch_snapshot = snap
                catcher = get_current_catcher(state)
                if catcher:
                    adjust_confidence(state, getattr(catcher, 'id', None), 2, reason="blocked_pitch", contagious=False)
                    adjust_battery_sync(state, self.pitcher_id, getattr(catcher, 'id', None), 0.12)
                adjust_confidence(state, getattr(self.pitcher, 'id', None), 1, reason="blocked_pitch")
            if state.balls == 4:
                _announce(self.bus, "MATCH_COMMENTARY", {
                    "text": "   >> WALK.",
                    "context": "walk",
                })
                was_slumping = get_confidence(state, self.batter_id) <= -30
                state.runners[0] = self.batter
                self.batter_stats["walks"] += 1
                self.pitcher_stats["walks"] += 1
                _apply_walk_confidence(state, self.batter, self.pitcher)
                record_pitcher_stress(state, self.pitcher_id, spike=True)
                record_rally_progress(state, self.offense_team_id, self.batter_id, reached_base=True)
                apply_slump_boost(state, self.batter_id, was_slumping, "walk")
                maybe_catcher_settle(state, self.pitcher_id)
                _trigger_presence(state, self.pitcher, "walk_batter", "Issued Walk")
                return "end"
            return "continue"

        if pitch_res.outcome == "Strike":
            if state.strikes < 2 or pitch_res.description != "Foul":
                state.strikes += 1
            if state.strikes == 3:
                _announce(self.bus, "MATCH_COMMENTARY", {
                    "text": "   >> STRIKEOUT!",
                    "context": "strikeout",
                })
                state.outs += 1
                self.batter_stats["strikeouts"] += 1
                self.pitcher_stats["strikeouts_pitched"] += 1
                if self.last_pitch_res and getattr(self.last_pitch_res, "full_count", False):
                    _trigger_presence(state, self.pitcher, "strikeout_full_count", "Full Count K")
                if bases_loaded_snapshot and outs_snapshot == 2:
                    _trigger_presence(state, self.pitcher, "escape_bases_loaded", "Bases Loaded Escape")
                if _is_cleanup(self.batter):
                    trigger_label = "Cleanup Silenced"
                    if self.last_pitch_res and self.last_pitch_res.description == "Swinging Miss":
                        _trigger_presence(state, self.batter, "strikeout_swinging", "Cleanup Whiffs")
                        trigger_label = "Cleanup Chased"
                    _trigger_presence(state, self.pitcher, "strikeout_cleanup", trigger_label)
                _maybe_comment_on_dominance(self.pitcher, tracker, self.pitcher_stats, bus=self.bus)
                _apply_strikeout_confidence(state, self.batter, self.pitcher)
                reset_slump_chain(state, self.batter_id)
                record_pitcher_stress(state, self.pitcher_id, spike=False)
                reset_rally_tracker(state, self.offense_team_id)
                _note_rivalry_strikeout(state, self.batter_id, self.pitcher_id, self.last_pitch_res)
                return "end"
            return "continue"

        if pitch_res.outcome == "Foul":
            if state.strikes < 2:
                state.strikes += 1
            return "continue"

        if pitch_res.outcome == "InPlay":
            return "contact"

        return "continue"

    def run(self):
        """Simulates one complete At-Bat."""
        state = self.state
        self._phase_setup()
        self._phase_rival_cutin()

        while True:
            self._emit_state(self.STATE_WINDUP, {
                "inning": state.inning,
                "half": state.top_bottom,
                "batter_id": self.batter_id,
                "pitcher_id": self.pitcher_id,
            })

            batter_action, batter_mods = self._phase_batter_decision()
            runner_status, batter_mods, slide_trait_mods = self._phase_runner_threats(batter_action, batter_mods)
            if runner_status == "end":
                break
            if runner_status == "restart":
                continue

            batter_trait_mods, pitcher_trait_mods = self._phase_prepare_traits(batter_mods, slide_trait_mods)
            bases_loaded_snapshot = _bases_loaded(state)
            outs_snapshot = state.outs

            pitch_res, tracker = self._phase_pitch(batter_action, batter_mods, batter_trait_mods, pitcher_trait_mods)
            resolution = self._phase_resolution(pitch_res, bases_loaded_snapshot, outs_snapshot, tracker, batter_trait_mods)
            if resolution == "continue":
                continue
            if resolution == "contact":
                self._phase_contact(pitch_res, batter_trait_mods, bases_loaded_snapshot, outs_snapshot)
                self._emit_phase(AtBatPhase.POST_PLAY, {
                    "inning": state.inning,
                    "half": state.top_bottom,
                    "batter_id": self.batter_id,
                    "pitcher_id": self.pitcher_id,
                })
                break
            if resolution == "end":
                self._emit_phase(AtBatPhase.POST_PLAY, {
                    "inning": state.inning,
                    "half": state.top_bottom,
                    "batter_id": self.batter_id,
                    "pitcher_id": self.pitcher_id,
                })
                break

        if callable(self.pressure_updater):
            self.pressure_updater()
        _broadcast_confidence_flashes(state, bus=self.bus)
        return


def start_at_bat(state):
    machine = AtBatStateMachine(state)
    machine.run()