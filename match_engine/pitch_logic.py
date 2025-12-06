import os
from types import SimpleNamespace
from typing import Any, Dict, Optional

from database.setup_db import PitchRepertoire, session_scope
from match_engine.pitch_definitions import PITCH_TYPES, ARM_SLOT_MODIFIERS
from match_engine.commentary import commentary_enabled
from game.rng import get_rng
from game.mechanics import (
    generate_unique_form,
    get_or_create_profile,
    mechanics_adjustment_for_pitch,
)
from game.skill_system import player_has_skill
from battery_system.battery_trust import adjust_battery_sync, get_battery_sync

# Toggle: allow battle-math logs to be pushed into at-bat feeds without always printing.
ADV_BATTLE_FEEDBACK = os.environ.get("ADV_BATTLE_FEEDBACK", "1") not in {"0", "false", "False"}

rng = get_rng()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _weather_effects(state):
    weather = getattr(state, "weather", None)
    return getattr(weather, "effects", None)


def _weather_adjusted_pitch_count(state, pitcher_id: Optional[int]) -> int:
    if not state or not pitcher_id:
        return 0
    base = getattr(state, "pitch_counts", {}).get(pitcher_id, 0)
    effects = _weather_effects(state)
    scalar = getattr(effects, "stamina_drain_scalar", 1.0) if effects else 1.0
    scalar = max(0.75, min(1.5, scalar))
    return int(round(base * scalar))


def _get_pitcher_presence(state, pitcher_id):
    if not state or not pitcher_id:
        return 0.0
    return getattr(state, "pitcher_presence", {}).get(pitcher_id, 0.0)


def _adjust_pitcher_presence(state, pitcher_id, delta: float) -> None:
    if not state or not pitcher_id or not delta:
        return
    presence = _get_pitcher_presence(state, pitcher_id) + delta
    state.pitcher_presence[pitcher_id] = _clamp(presence, -4.0, 4.0)


def _get_sequence_bucket(state, pitcher_id):
    if not state or not pitcher_id:
        return {"last": None, "by_batter": {}}
    bucket = state.pitch_sequence_memory.setdefault(pitcher_id, {"last": None, "by_batter": {}})
    bucket.setdefault("by_batter", {})
    return bucket


def _velocity_band(velocity: float) -> str:
    if velocity >= 150:
        return "elite"
    if velocity >= 140:
        return "plus"
    if velocity >= 130:
        return "avg"
    return "slow"


def _evaluate_pitch_tunneling(state, pitcher_id, batter_id, pitch_name, pitch_def, location):
    bucket = _get_sequence_bucket(state, pitcher_id)
    last_vs_batter = bucket["by_batter"].get(batter_id)
    repeat_penalty = 0.0
    tunneling_bonus = 0.0
    repeat_count = 0
    family = pitch_def.get("family", "Generic")
    if last_vs_batter:
        repeat_count = last_vs_batter.get("repeat", 0)
        if last_vs_batter.get("pitch_name") == pitch_name and last_vs_batter.get("location") == location:
            repeat_penalty = 6 + repeat_count * 3
        elif last_vs_batter.get("family") == family and location == last_vs_batter.get("location"):
            repeat_penalty = 4
        else:
            prev_family = last_vs_batter.get("family")
            prev_loc = last_vs_batter.get("location")
            if prev_family == "Fastball" and family in {"Breaker", "Changeup", "Splitter"} and prev_loc == "Zone" and location == "Chase":
                tunneling_bonus = 9
            elif prev_family in {"Breaker", "Changeup", "Splitter"} and family == "Fastball" and location == "Zone":
                tunneling_bonus = 6
            elif prev_family == "Fastball" and family == "Fastball" and prev_loc != location:
                tunneling_bonus = 3
    return repeat_penalty, tunneling_bonus, repeat_count


def _commit_sequence_memory(state, pitcher_id, batter_id, pitch_name, pitch_def, location, velocity):
    bucket = _get_sequence_bucket(state, pitcher_id)
    prev = bucket["by_batter"].get(batter_id)
    if prev and prev.get("pitch_name") == pitch_name and prev.get("location") == location:
        repeat = prev.get("repeat", 1) + 1
    else:
        repeat = 1
    entry = {
        "pitch_name": pitch_name,
        "family": pitch_def.get("family", "Generic"),
        "location": location,
        "velocity_band": _velocity_band(velocity),
        "repeat": repeat,
    }
    bucket["by_batter"][batter_id] = entry
    bucket["last"] = entry


def get_last_pitch_call(state, pitcher_id, batter_id=None):
    bucket = _get_sequence_bucket(state, pitcher_id)
    if batter_id is not None:
        return bucket["by_batter"].get(batter_id)
    return bucket.get("last")


def _note_batter_behavior(state, batter_id, *, times_faced=1, chase_swing=False, zone_take=False, hard_contact=False,
                          disciplined_take=False, late_on_heat=False, aggressive_early=False, clip_label=None):
    if not state or not batter_id:
        return
    tracker = state.batter_tell_tracker.setdefault(batter_id, {
        "seen": 0,
        "chase_swings": 0,
        "zone_takes": 0,
        "hard_contact": 0,
        "disciplined": 0,
        "late_heat": 0,
        "aggressive": 0,
        "last_clip": None,
    })
    tracker["seen"] = max(tracker.get("seen", 0), times_faced)
    if chase_swing:
        tracker["chase_swings"] += 1
    if zone_take:
        tracker["zone_takes"] += 1
    if hard_contact:
        tracker["hard_contact"] += 1
    if disciplined_take:
        tracker["disciplined"] += 1
    if late_on_heat:
        tracker["late_heat"] += 1
    if aggressive_early:
        tracker["aggressive"] += 1
    if clip_label:
        tracker["last_clip"] = clip_label


def describe_batter_tells(state, batter):
    batter_id = getattr(batter, "id", None)
    hints = []
    tracker = None
    if state and batter_id:
        tracker = getattr(state, "batter_tell_tracker", {}).get(batter_id)
    if tracker:
        seen = tracker.get("seen", 0)
        if seen >= 2:
            hints.append(f"Seen {seen}x this game")
        if tracker.get("chase_swings", 0) >= 2:
            hints.append("Chasing off the plate")
        elif tracker.get("disciplined", 0) >= 2:
            hints.append("Laying off chase pitches")
        if tracker.get("late_heat", 0) >= 2:
            hints.append("Late on high velocity")
        if tracker.get("hard_contact", 0) >= 1:
            hints.append("Timed a mistake last AB")
        if tracker.get("zone_takes", 0) >= 1:
            hints.append("Taking strikes")
        if tracker.get("aggressive", 0) >= 2:
            hints.append("Jumping early counts")
        if tracker.get("last_clip") and len(hints) < 3:
            hints.append(tracker["last_clip"])
        return hints[:3]

    discipline = getattr(batter, "discipline", 50) or 50
    contact = getattr(batter, "contact", 50) or 50
    power = getattr(batter, "power", 50) or 50
    if discipline < 45:
        hints.append("Will expand early")
    elif discipline > 65:
        hints.append("Patient eye")
    if power >= 70:
        hints.append("Punishes mistakes")
    elif contact >= 70:
        hints.append("Puts everything in play")
    return hints[:3]


def _normalize_call(call_result, default_trust=55):
    if hasattr(call_result, "pitch"):
        return call_result
    if isinstance(call_result, tuple) and len(call_result) >= 2:
        pitch, location = call_result[:2]
    else:
        pitch = call_result
        location = "Zone"
    return SimpleNamespace(
        pitch=pitch,
        location=location,
        intent="Manual",
        shakes=0,
        trust=default_trust,
        forced=False,
    )


def _player_team_id(player):
    return getattr(player, 'team_id', getattr(player, 'school_id', None))


def _offense_team_id(state):
    return getattr(state.away_team, 'id', None) if getattr(state, 'top_bottom', 'Top') == 'Top' else getattr(state.home_team, 'id', None)


def _defense_team_id(state):
    return getattr(state.home_team, 'id', None) if getattr(state, 'top_bottom', 'Top') == 'Top' else getattr(state.away_team, 'id', None)


def _flow_multiplier(state, team_id):
    system = getattr(state, "momentum_system", None)
    if not system or team_id is None:
        return 1.0
    return system.get_multiplier(team_id)


def _annotate_result(result: PitchResult, count_snapshot: tuple[int, int]):
    result.count_before = count_snapshot
    result.full_count = count_snapshot == (3, 2)
    return result


_OFFSPEED_FAMILIES = {"changeup", "splitter", "forkball"}


def _guess_matches(payload: dict | None, pitch_def: dict, location: str) -> bool | None:
    if not payload:
        return None
    kind = (payload.get("kind") or "").lower()
    target = (payload.get("value") or "").lower()
    if not kind or not target:
        return None
    if kind == "family":
        family = (pitch_def.get("family") or "").lower()
        if not family:
            return None
        if target == "offspeed":
            return family in _OFFSPEED_FAMILIES
        return family == target
    if kind == "location":
        actual = "zone" if location == "Zone" else "chase"
        return actual == target
    return None


def _runner_on_base(state, slot: int):
    runners = getattr(state, "runners", None)
    if not runners:
        return None
    if slot < 0 or slot >= len(runners):
        return None
    return runners[slot]


def _baserunning_aura_penalty(state) -> float:
    if not state or _defense_team_id(state) == 1:
        return 0.0
    runner = _runner_on_base(state, 0)
    if not runner or _player_team_id(runner) != 1:
        return 0.0
    speed = getattr(runner, "speed", 50) or 50
    if speed < 72:
        return 0.0
    return 10.0


def _record_umpire_bias(state, favored_role: str) -> None:
    plate = getattr(state, 'umpire_plate_summary', None)
    if plate is None:
        plate = {
            'offense': {'favored': 0, 'squeezed': 0},
            'defense': {'favored': 0, 'squeezed': 0},
        }
        state.umpire_plate_summary = plate
    other = 'defense' if favored_role == 'offense' else 'offense'
    plate.setdefault(favored_role, {'favored': 0, 'squeezed': 0})['favored'] += 1
    plate.setdefault(other, {'favored': 0, 'squeezed': 0})['squeezed'] += 1
    favored_id = _offense_team_id(state) if favored_role == 'offense' else _defense_team_id(state)
    penalized_id = _defense_team_id(state) if favored_role == 'offense' else _offense_team_id(state)
    tilt_map = getattr(state, 'umpire_call_tilt', None)
    if tilt_map is None:
        tilt_map = {}
        state.umpire_call_tilt = tilt_map
    for team_id, field in ((favored_id, 'favored'), (penalized_id, 'squeezed')):
        if team_id is None:
            continue
        tracker = tilt_map.setdefault(team_id, {'favored': 0, 'squeezed': 0})
        tracker[field] += 1


def _call_noise_window(umpire) -> float:
    temperament = getattr(umpire, "temperament", 0.5) or 0.5
    consistency = getattr(umpire, "consistency", 0.7) or 0.7
    base = 0.25 + temperament * 0.2
    spread = base * (1.6 - max(0.0, min(1.0, consistency)))
    return max(0.05, spread)


def _catcher_receiving_score(catcher) -> float:
    if not catcher:
        return 0.0
    fielding = getattr(catcher, "fielding", 55) or 55
    leadership = getattr(catcher, "catcher_leadership", 50) or 50
    discipline = getattr(catcher, "discipline", 50) or 50
    throwing = getattr(catcher, "throwing", 50) or 50
    composite = (fielding * 0.45) + (leadership * 0.3) + (discipline * 0.15) + (throwing * 0.1)
    normalized = (composite - 55.0) / 25.0
    return max(-1.0, min(1.0, normalized))


def _framing_adjustment(state, umpire, base_score: float, location: str) -> float:
    factor = getattr(umpire, "framing_factor", 0.0) or 0.0
    if not factor:
        return 0.0
    catcher = get_current_catcher(state)
    score = _catcher_receiving_score(catcher)
    if not score:
        return 0.0
    leverage = max(0.0, 1.4 - abs(base_score))
    if leverage <= 0:
        return 0.0
    return leverage * score * factor


def _log_umpire_call(state, call: str, default: str, flipped: bool, location: str) -> None:
    ledger = getattr(state, "umpire_recent_calls", None)
    if ledger is None:
        ledger = []
        state.umpire_recent_calls = ledger
    entry = {
        "inning": getattr(state, "inning", 0),
        "half": getattr(state, "top_bottom", "Top"),
        "call": call,
        "default": default,
        "flipped": flipped,
        "location": location,
        "balls": getattr(state, "balls", 0),
        "strikes": getattr(state, "strikes", 0),
    }
    ledger.append(entry)
    if len(ledger) > 12:
        del ledger[0]


class PitchResult:
    def __init__(self, pitch_name, location, outcome, description, velocity=0):
        self.pitch_name = pitch_name
        self.location = location  # "Zone" or "Chase"
        self.outcome = outcome  # "Ball", "Strike", "Foul", "InPlay"
        self.description = description  # "Swinging Miss", "Looking", "Weak Grounder"
        self.velocity = velocity
        self.in_zone = location == "Zone"
        self.zone_label = "IN" if self.in_zone else "OUT"
        self.contact_quality = 0  # Default
        self.special = None
        self.argument_penalty = 0
        self.argument_target_id = None
        self.argument_ejection = False
        self.count_before: tuple[int, int] = (0, 0)
        self.full_count: bool = False
        self.guess_payload: dict | None = None
        self.battery_call: dict | None = None
        self.bunt_intent = None
        self.mechanics_tags: tuple[str, ...] = ()


def _record_catcher_memory(state, batter_id: Optional[int], result: PitchResult) -> None:
    memory = getattr(state, "catcher_memory", None)
    if not memory or not hasattr(memory, "record"):
        return
    outcome_flag = _memory_outcome_tag(result)
    if not outcome_flag:
        return
    try:
        memory.record(batter_id, result.pitch_name, outcome=outcome_flag, location=result.location)
    except Exception:
        # Memory logging is non-critical; swallow unexpected errors.
        return


def _memory_outcome_tag(result: PitchResult) -> Optional[str]:
    if result.outcome == "Strike":
        if result.description == "Swinging Miss":
            return "whiff"
        return "strike"
    if result.outcome == "Ball":
        return "ball"
    if result.outcome == "Foul":
        return "chase" if result.location == "Chase" else "strike"
    if result.outcome == "InPlay":
        quality = getattr(result, "contact_quality", 0)
        return "hard_contact" if quality >= 35 else "weak_contact"
    return None


def _maybe_flag_wild_pitch(result, state, pitcher):
    weather = getattr(state, 'weather', None)
    if result.outcome != "Ball" or not any(state.runners):
        return
    control = getattr(pitcher, 'control', 50) or 50
    fatigue = max(0, _weather_adjusted_pitch_count(state, getattr(pitcher, 'id', None)) - 85)
    weather_push = getattr(weather, 'wild_pitch_modifier', 0.0) if weather else 0.0
    effects = _weather_effects(state)
    slip_bonus = getattr(effects, 'ball_slip_chance', 0.0) if effects else 0.0
    base = max(0.0, (60 - control) * 0.0025)
    fatigue_bonus = fatigue * 0.001
    chance = base + fatigue_bonus
    if weather_push >= 0:
        chance += weather_push * 1.2
    else:
        chance += weather_push * 0.6
    if slip_bonus:
        chance += slip_bonus * 0.8
    chance = max(0.0, min(0.35, chance))
    if rng.random() < chance:
        result.description = "Wild Pitch"
        result.special = "wild_pitch"


def _maybe_mark_close_call(state, participant, result, took_pitch: bool, role: str = "batter", leverage: float = 1.0):
    if not participant or not took_pitch or result.outcome not in {"Strike", "Ball"}:
        return
    chance = 0.15
    if role == "pitcher":
        chance = 0.10
    umpire = getattr(state, "umpire", None)
    if umpire:
        chance *= 0.7 + getattr(umpire, "temperament", 0.5)
    chance *= leverage
    if rng.random() > chance:
        return
    penalty, ejected = _register_argument_penalty(state, participant)
    if not penalty and not ejected:
        return
    result.special = f"argument_{role}"
    result.argument_penalty = penalty
    result.argument_target_id = getattr(participant, "id", None)
    result.argument_ejection = ejected


def _register_argument_penalty(state, participant) -> tuple[int, bool]:
    volatility = getattr(participant, "volatility", 50) or 50
    if volatility < 65:
        return 0, False
    cooldowns = getattr(state, "argument_cooldowns", None)
    pid = getattr(participant, "id", None)
    if cooldowns is None or pid is None:
        return 0, False
    inning = getattr(state, "inning", 0)
    if cooldowns.get(pid) == inning:
        return 0, False
    umpire = getattr(state, "umpire", None)
    temperament = getattr(umpire, "temperament", 0.5) if umpire else 0.5
    chance = 0.07 + max(0.0, (volatility - 65) / 30.0) * 0.25
    chance *= 0.75 + temperament
    if _is_pressure_cooker(state):
        chance += 0.05
    if rng.random() > chance:
        return 0, False
    cooldowns[pid] = inning
    penalty = 6 + int(max(0, volatility - 60) / 2.5)
    penalty = min(18, penalty)
    ejection_chance = max(0.0, (volatility - 78) / 45.0)
    ejection_chance *= 0.65 + temperament
    if _is_pressure_cooker(state):
        ejection_chance += 0.05
    ejected = rng.random() < ejection_chance
    _adjust_umpire_mood(state, -0.05 * (1 + temperament))
    if ejected:
        _adjust_umpire_mood(state, -0.08 * (1 + temperament))
    return penalty, ejected


def _bases_loaded(state) -> bool:
    runners = getattr(state, "runners", None)
    if not runners or len(runners) < 3:
        return False
    return all(runner is not None for runner in runners)


def _is_clutch_situation(state) -> bool:
    if not state:
        return False
    if getattr(state, "inning", 0) < 7:
        return False
    if not _bases_loaded(state):
        return False
    score_gap = abs((getattr(state, "home_score", 0) or 0) - (getattr(state, "away_score", 0) or 0))
    return score_gap <= 3


def _is_pressure_cooker(state) -> bool:
    inning = getattr(state, "inning", 1)
    score_gap = abs((state.home_score or 0) - (state.away_score or 0))
    runners = getattr(state, "runners", None)
    runners_in_scoring_pos = any(runners[1:]) if runners else False
    late = inning >= 7
    return (late and score_gap <= 2) or runners_in_scoring_pos


def _adjust_umpire_mood(state, delta: float) -> None:
    if not hasattr(state, "umpire_mood"):
        return
    mood = getattr(state, "umpire_mood", 0.0) or 0.0
    mood += delta
    state.umpire_mood = max(-0.6, min(0.6, mood))


def _apply_clutch_bonus(control: float, movement: float, velocity: float, quality: float) -> tuple[float, float, float, str]:
    swing = quality - 0.5
    control += swing * 36.0
    movement += swing * 12.0
    velocity += swing * 4.0
    special = ""
    if quality >= 0.9:
        control += 8.0
        movement += 6.0
        special = "clutch_paint"
    elif quality <= 0.2:
        control -= 10.0
        movement -= 4.0
        special = "clutch_miss"
    return control, movement, velocity, special


def _consume_clutch_pitch_effect(state, pitcher_id: Optional[int]) -> Optional[Dict[str, Any]]:
    consumer = getattr(state, "consume_clutch_pitch_effect", None)
    if not callable(consumer):
        return None
    return consumer(pitcher_id)


def _call_with_umpire_bias(state, location: str) -> tuple[str, bool]:
    """Return the called outcome (Strike/Ball) and whether it defied the default zone."""
    default = "Strike" if location == "Zone" else "Ball"
    umpire = getattr(state, "umpire", None)
    if not umpire:
        return default, False
    pitcher_is_home = getattr(state, "top_bottom", "Top") == "Top"
    zone_bias = getattr(umpire, "zone_bias", 0.0) or 0.0
    home_bias = getattr(umpire, "home_bias", 0.0) or 0.0
    mood = getattr(state, "umpire_mood", 0.0) or 0.0

    strictness = getattr(umpire, "strictness", 0.5) or 0.5
    tightness = (strictness - 0.5) * 0.8
    base = 1.15 + tightness
    if location != "Zone":
        base = -base
    base -= zone_bias
    if home_bias:
        base += home_bias if pitcher_is_home else -home_bias
    base += mood
    base += _framing_adjustment(state, umpire, base, location)
    swing = _call_noise_window(umpire)
    base += rng.uniform(-swing, swing)
    call = "Strike" if base >= 0 else "Ball"
    flipped = call != default
    # drift mood slightly toward neutrality unless challenged again
    if flipped:
        favored_role = "defense" if call == "Strike" else "offense"
        _record_umpire_bias(state, favored_role)
        drift = -0.05 if call == "Strike" else 0.07
        consistency = getattr(umpire, "consistency", 0.7) or 0.7
        _adjust_umpire_mood(state, drift * (1.05 - (consistency * 0.3)))
    else:
        _adjust_umpire_mood(state, mood * -0.15)
    _log_umpire_call(state, call, default, flipped, location)
    return call, flipped

def get_arsenal(pitcher_id):
    with session_scope() as session:
        pitches = session.query(PitchRepertoire).filter_by(player_id=pitcher_id).all()
    if not pitches:
        # Default Arsenal if none found
        return [
            PitchRepertoire(pitch_name="4-Seam Fastball", quality=40, break_level=10),
            PitchRepertoire(pitch_name="Slider", quality=30, break_level=40),
        ]
    return pitches

def get_current_catcher(state):
    """
    Helper to find the catcher for the defensive team.
    """
    if state.top_bottom == "Top":
        # Home Team is pitching
        lineup = state.home_lineup
    else:
        # Away Team is pitching
        lineup = state.away_lineup
        
    # Find player with position 'Catcher'
    for p in lineup:
        if p.position == "Catcher":
            return p
            
    # Fallback: Just return the first player if no catcher defined (e.g. testing)
    return lineup[0] if lineup else None

def resolve_pitch(
    pitcher,
    batter,
    state,
    batter_action="Normal",
    batter_mods=None,
    *,
    batter_trait_mods=None,
    pitcher_trait_mods=None,
    batter_tendencies=None,
    times_through_order: int = 1,
):
    """
    Calculates the physics of the pitch vs the batter.
    Now integrates the BATTERY SYSTEM for pitch selection.
    """
    if batter_mods is None:
        batter_mods = {}
    batter_trait_mods = batter_trait_mods or {}
    pitcher_trait_mods = pitcher_trait_mods or {}
    batter_tendencies = batter_tendencies or {}

    updater = getattr(state, "update_pressure_index", None)
    if callable(updater):
        updater()

    from match_engine.confidence import get_confidence

    times_through_order = max(1, times_through_order or 1)
    pitcher_id = getattr(pitcher, 'id', None)
    batter_id = getattr(batter, 'id', None)
    count_snapshot = (state.balls, state.strikes)
    psychology_engine = getattr(state, "psychology_engine", None)

    # --- 1. PITCH SELECTION (BATTERY NEGOTIATION) ---
    catcher = get_current_catcher(state)

    from battery_system.battery_negotiation import run_battery_negotiation
    
    if catcher:
        call_result = run_battery_negotiation(pitcher, catcher, batter, state)
    else:
        from player_roles.pitcher_controls import player_pitch_turn
        call_result = player_pitch_turn(pitcher, batter, state)

    negotiated = _normalize_call(call_result)
    pitch = negotiated.pitch
    location = negotiated.location
    shakes = getattr(negotiated, 'shakes', 0)
    trust_snapshot = getattr(negotiated, 'trust', 55) or 55
    forced_call = bool(getattr(negotiated, 'forced', False))
    catcher_id = getattr(catcher, 'id', None)

    battery_context = {}
    previous_call = getattr(state, "last_battery_call", None)
    if isinstance(previous_call, dict):
        battery_context.update(previous_call)
    perfect_location = bool(getattr(negotiated, "perfect_location", False))

    battery_context.update(
        {
            "pitcher_id": pitcher_id,
            "catcher_id": catcher_id,
            "batter_id": batter_id,
            "pitch_name": getattr(pitch, "pitch_name", getattr(pitch, "name", None)),
            "location": location,
            "intent": getattr(negotiated, "intent", "Normal"),
            "shakes": shakes,
            "trust": trust_snapshot,
            "forced": forced_call,
        }
    )
    battery_sync_value = battery_context.get("sync")
    if battery_sync_value is None:
        battery_sync_value = get_battery_sync(state, pitcher_id, catcher_id)
        battery_context["sync"] = battery_sync_value

    # --- 2. PITCH PHYSICS ---
    p_def = PITCH_TYPES.get(pitch.pitch_name, PITCH_TYPES["4-Seam Fastball"])

    mechanics_profile = None
    form_effect = None
    extension_bonus = 0.0
    hiding_factor = 1.0
    mechanics_tags: tuple[str, ...] = ()
    mechanics_deception = 0.0
    perception_penalty = 0.0
    try:
        mechanics_profile = get_or_create_profile(state, pitcher)
        form_effect = generate_unique_form(pitcher, profile=mechanics_profile)
        if form_effect:
            extension_ft = float(form_effect.get("extension", 6.0) or 6.0)
            extension_bonus = max(-1.2, min(2.8, (extension_ft - 6.0) * 0.45))
            hiding_factor = float(form_effect.get("hiding_factor", 1.0) or 1.0)
    except Exception:
        mechanics_profile = None
    
    # Arm Slot Mods
    arm_slot = getattr(pitcher, 'arm_slot', 'Three-Quarters')
    if mechanics_profile and getattr(mechanics_profile, "arm_slot", None):
        arm_slot = mechanics_profile.arm_slot
    slot_mods = ARM_SLOT_MODIFIERS.get(arm_slot, ARM_SLOT_MODIFIERS["Three-Quarters"])
    slot_group = slot_mods.get('group', 'Neutral')
    plane = p_def.get('plane', 'ride')
    plane_bonus = slot_mods.get('plane_bonus', {}).get(plane, 1.0)
    slot_group_bonus = (p_def.get('slot_groups') or {}).get(slot_group, (p_def.get('slot_groups') or {}).get('Any', 1.0))
    sequence_penalty, tunneling_bonus, _repeat_count = _evaluate_pitch_tunneling(
        state,
        pitcher_id,
        batter_id,
        pitch.pitch_name,
        p_def,
        location,
    )
    dominance = _get_pitcher_presence(state, pitcher_id)
    tto_stage = max(0, times_through_order - 1)
    
    # Fatigue Calculation
    adj_pitch_count = _weather_adjusted_pitch_count(state, pitcher_id)
    fatigue_penalty = 0
    control_penalty = 0
    
    if adj_pitch_count > 80: fatigue_penalty = (adj_pitch_count - 80) * 0.2
    if adj_pitch_count > 100: fatigue_penalty += (adj_pitch_count - 100) * 0.5
    if adj_pitch_count > 90: control_penalty = (adj_pitch_count - 90) * 0.5
    
    weather = getattr(state, 'weather', None)
    weather_effects = _weather_effects(state)

    # Final Values
    base_velocity = (getattr(pitcher, 'velocity', 0) or 0) + pitcher_trait_mods.get('velocity', 0)
    velocity = (base_velocity * p_def['velocity_mod']) - fatigue_penalty
    if extension_bonus:
        velocity += extension_bonus
    base_movement = pitch.break_level * p_def['break_mod']
    movement_plane_mult = 1.0
    if p_def['type'] in ["Vertical", "Drop_Sink"]:
        movement_plane_mult = slot_mods['vertical_mult']
    elif p_def['type'] == "Horizontal":
        movement_plane_mult = slot_mods['horizontal_mult']
    else:
        movement_plane_mult = (slot_mods['vertical_mult'] + slot_mods['horizontal_mult']) / 2.0
    effective_movement = base_movement * movement_plane_mult * plane_bonus * slot_group_bonus

    base_control = (getattr(pitcher, 'control', 50) or 50) + pitcher_trait_mods.get('control', 0)
    effective_control = (base_control * slot_mods['control_penalty_mult']) - control_penalty
    if mechanics_profile:
        mech_adj = mechanics_adjustment_for_pitch(mechanics_profile, p_def, location=location)
        velocity += mech_adj.velocity_bonus
        effective_control += mech_adj.control_bonus
        effective_movement *= mech_adj.movement_scalar
        mechanics_deception = mech_adj.deception_bonus
        perception_penalty = mech_adj.perception_penalty
        mechanics_tags = mech_adj.tags
    if weather:
        effective_control -= weather.wild_pitch_modifier * 60
    if weather_effects and weather_effects.ball_slip_chance:
        effective_control -= weather_effects.ball_slip_chance * 35
    pitch_confidence = get_confidence(state, pitcher.id)
    effective_control += pitch_confidence * 0.25
    velocity += pitch_confidence * 0.05
    if dominance:
        effective_control += dominance * 1.25
        effective_movement += dominance * 1.4
    if tto_stage:
        effective_control -= 4 * tto_stage
        velocity -= tto_stage * 0.5

    if shakes:
        tension = shakes * max(0.8, (65 - trust_snapshot) / 10.0)
        tension *= 1.0 - (dominance * 0.05)
        sync_buffer = max(0.6, 1.0 - (battery_sync_value * 0.08))
        effective_control -= tension * 1.5 * sync_buffer
        effective_movement -= tension * 0.5 * sync_buffer
    elif trust_snapshot > 65:
        sync_bonus = 1.0 + max(0.0, battery_sync_value) * 0.08
        effective_control += (trust_snapshot - 65) * 0.15 * sync_bonus
        effective_movement += (trust_snapshot - 65) * 0.05 * sync_bonus

    if forced_call:
        forced_penalty = 3 + max(0.0, -battery_sync_value) * 0.5
        effective_control -= forced_penalty
        effective_movement -= forced_penalty * 0.2

    flow_offense = _flow_multiplier(state, _offense_team_id(state))
    flow_defense = _flow_multiplier(state, _defense_team_id(state))
    if flow_defense != 1.0:
        effective_control *= flow_defense
        effective_movement *= flow_defense
        velocity *= flow_defense

    aura_penalty = _baserunning_aura_penalty(state)
    if aura_penalty:
        effective_control -= aura_penalty
        logs = getattr(state, "logs", None)
        runner = _runner_on_base(state, 0)
        if isinstance(logs, list) and runner:
            logs.append(f"[Field General] {getattr(runner, 'name', 'Runner')} toys with the pitcher on first. Control -10.")

    pitcher_pressure = state.pressure_penalty(pitcher, "pitcher") if hasattr(state, "pressure_penalty") else 0.0
    if pitcher_pressure:
        control_factor = max(0.4, 1.0 - pitcher_pressure)
        effective_control *= control_factor
        effective_movement *= control_factor
        velocity *= max(0.6, 1.0 - pitcher_pressure * 0.5)

    clutch_effect = _consume_clutch_pitch_effect(state, pitcher_id)
    if clutch_effect:
        quality = float(clutch_effect.get("quality", 0.5) or 0.0)
        effective_control, effective_movement, velocity, special = _apply_clutch_bonus(
            effective_control,
            effective_movement,
            velocity,
            quality,
        )
        clutch_effect["special"] = special
        clutch_effect["applied_inning"] = getattr(state, "inning", 1)
        if isinstance(getattr(state, "logs", None), list):
            state.logs.append(
                f"[Showtime] {clutch_effect.get('team_name', 'Pitcher')} rides quality {quality:.2f} ({clutch_effect.get('feedback')})."
            )
        state.last_clutch_pitch_effect = dict(clutch_effect)

    # Synchronized Pitch: perfect location once per game for bonded battery
    if perfect_location:
        effective_control += 25
        effective_movement += 6
        location = "Zone"
        battery_context["perfect_location"] = True
        if isinstance(getattr(state, "logs", None), list):
            state.logs.append("[Battery Bond] Synchronized Pitch fired — paint job guaranteed.")

    # --- 3. BATTER REACTION ---
    pitcher_psych = psychology_engine.pitcher_modifiers(pitcher_id) if psychology_engine else None
    batter_psych = psychology_engine.batter_modifiers(batter_id) if psychology_engine else None
    if pitcher_psych:
        effective_control += pitcher_psych.control_bonus
        effective_movement += pitcher_psych.movement_bonus
        velocity += pitcher_psych.velocity_bonus
    
    # Apply mods (from User Choice or AI buffs)
    speech_buffs = getattr(state, "captains_speech_buffs", {}) or {}
    offense_buff = speech_buffs.get(_offense_team_id(state))
    defense_buff = speech_buffs.get(_defense_team_id(state))

    base_eye = getattr(batter, 'eye', getattr(batter, 'discipline', 50)) or 50
    base_eye += batter_trait_mods.get('discipline', 0) + batter_trait_mods.get('eye', 0)
    eye_stat = base_eye + batter_mods.get('eye_mod', 0)
    base_contact = getattr(batter, 'contact', 50) or 50
    base_contact += batter_trait_mods.get('contact', 0)
    contact_stat = base_contact + batter_mods.get('contact_mod', 0)
    if offense_buff:
        eye_stat += offense_buff.get("eye", 0)
        contact_stat += offense_buff.get("contact", 0)
        batter_mods['power_mod'] = batter_mods.get('power_mod', 0) + offense_buff.get("power", 0)
    if batter_psych:
        eye_stat *= batter_psych.eye_scalar
        contact_stat *= batter_psych.contact_scalar
    if defense_buff:
        effective_control += defense_buff.get("control", 0)
        effective_movement += defense_buff.get("movement", 0)

    rivalry_ctx = getattr(state, "rival_match_context", None)
    if rivalry_ctx and batter_id:
        rival_bonus = rivalry_ctx.recognition_bonus(batter_id, pitch.pitch_name)
        if rival_bonus:
            eye_stat *= 1.0 + rival_bonus
            contact_stat *= 1.0 + rival_bonus
            memo_key = f"rival_bonus_{batter_id}"
            memory = getattr(state, "commentary_memory", None)
            if isinstance(memory, set) and memo_key not in memory:
                memory.add(memo_key)
                logs = getattr(state, "logs", None)
                if isinstance(logs, list):
                    logs.append(
                        f"[Rivals] {getattr(batter, 'last_name', getattr(batter, 'name', 'Rival'))} refuses to chase that {pitch.pitch_name} again."
                    )

        if rivalry_ctx.is_rival_plate(batter_id) and rivalry_ctx.is_hero_pitching(pitcher_id):
            effective_control -= 6
            effective_movement -= 2
            perception_penalty += 4
            memory = getattr(state, "commentary_memory", None)
            memo_key = "rival_nerves"
            if isinstance(memory, set) and memo_key not in memory:
                memory.add(memo_key)
                logs = getattr(state, "logs", None)
                if isinstance(logs, list):
                    logs.append("[Rivals] Hands shake — safe zone shrinks under rival glare.")

    guess_payload = batter_mods.get('guess_payload')
    guess_match = _guess_matches(guess_payload, p_def, location) if guess_payload else None
    guess_source = (guess_payload or {}).get('source', 'user')
    if guess_match is True:
        if guess_source == 'ai':
            eye_stat *= 1.12
            contact_stat *= 1.18
            batter_mods['power_mod'] = batter_mods.get('power_mod', 0) + 15
        else:
            eye_stat *= 1.25
            contact_stat *= 1.35
            batter_mods['power_mod'] = batter_mods.get('power_mod', 0) + 30
        guess_payload['result'] = 'locked_in'
    elif guess_match is False:
        if guess_source == 'ai':
            eye_stat *= 0.78
            contact_stat *= 0.75
            batter_mods['power_mod'] = batter_mods.get('power_mod', 0) - 12
        else:
            eye_stat *= 0.6
            contact_stat *= 0.65
            batter_mods['power_mod'] = batter_mods.get('power_mod', 0) - 25
        guess_payload['result'] = 'fooled'

    def _apply_battery_feedback(res_obj: PitchResult) -> None:
        if not battery_context:
            return
        pitcher_key = battery_context.get("pitcher_id")
        catcher_key = battery_context.get("catcher_id")
        if not pitcher_key or not catcher_key:
            return
        delta = 0.0
        if res_obj.outcome == "Strike":
            delta += 0.12
            if res_obj.description == "Swinging Miss":
                delta += 0.08
        elif res_obj.outcome == "Ball":
            delta -= 0.12
        elif res_obj.outcome == "Foul":
            delta += 0.05 if res_obj.location == "Chase" else -0.02
        elif res_obj.outcome == "InPlay":
            quality = getattr(res_obj, "contact_quality", 0)
            delta += 0.1 if quality < 20 else -0.2
        if battery_context.get("forced"):
            delta -= 0.25
        elif battery_context.get("shakes"):
            delta -= 0.05 * battery_context["shakes"]
        else:
            delta += 0.05
        if not delta:
            return
        new_sync = adjust_battery_sync(state, pitcher_key, catcher_key, delta)
        battery_context["sync"] = new_sync
        res_obj.battery_call = dict(battery_context)
        setattr(state, "last_battery_call", dict(battery_context))

    def _finalize_result(res_obj: PitchResult) -> PitchResult:
        _annotate_result(res_obj, count_snapshot)
        # Attach pitch metadata for downstream UI/log consumers
        res_obj.pitch_family = p_def.get("family", "Unknown")
        res_obj.pitch_plane = p_def.get("plane", "?")
        res_obj.arm_slot = arm_slot
        res_obj.slot_group = slot_group
        res_obj.pitch_desc = p_def.get("desc")
        if perfect_location:
            res_obj.special = "synchronized_pitch"
        if guess_payload:
            res_obj.guess_payload = dict(guess_payload)
        if battery_context:
            battery_context.update(
                {
                    "outcome": res_obj.outcome,
                    "result_description": res_obj.description,
                }
            )
            res_obj.battery_call = dict(battery_context)
            setattr(state, "last_battery_call", dict(battery_context))
        _record_catcher_memory(state, batter_id, res_obj)
        _apply_battery_feedback(res_obj)
        if mechanics_tags:
            res_obj.mechanics_tags = tuple(mechanics_tags)
        if psychology_engine:
            leverage = 1.0 + max(0.0, getattr(state, "pressure_index", 0.0)) / 10.0
            psychology_engine.record_pitch(pitcher_id, batter_id, res_obj, leverage=leverage)
        return res_obj

    if flow_offense != 1.0:
        eye_stat *= flow_offense
        contact_stat *= flow_offense

    batter_pressure = state.pressure_penalty(batter, "batter") if hasattr(state, "pressure_penalty") else 0.0
    if batter_pressure:
        penalty_factor = max(0.5, 1.0 - batter_pressure)
        eye_stat *= penalty_factor
        contact_stat *= penalty_factor

    if player_has_skill(batter, "clutch_hitter") and _is_clutch_situation(state):
        contact_stat *= 1.1
        batter_mods['power_mod'] = batter_mods.get('power_mod', 0) + 5
    
    reaction = eye_stat + rng.randint(-10, 10) - perception_penalty
    if hiding_factor != 1.0:
        reaction -= (hiding_factor - 1.0) * 14.0
    bat_control = contact_stat + rng.randint(-15, 15)
    batter_conf = get_confidence(state, batter.id)
    reaction += batter_conf * 0.2
    bat_control += batter_conf * 0.3
    if tto_stage:
        reaction += 3 * tto_stage
        bat_control += 4 * tto_stage
    
    # DECISION: SWING OR TAKE?
    should_swing = False
    
    swing_tendency = max(0.5, min(2.0, batter_tendencies.get('swing_aggression', 1.0)))
    if offense_buff and offense_buff.get("aggression_mult"):
        swing_tendency *= offense_buff["aggression_mult"]
    if _player_team_id(batter) == 1:
        # USER BATTER: Based on input action
        if batter_action in ["Swing", "Power", "Contact"]:
            should_swing = True
        elif batter_action == "Take":
            should_swing = False
    else:
        # AI BATTER: Based on location & reaction
        if location == "Zone":
            should_swing = True
        elif location == "Chase":
            chase_bar = (50 + effective_movement / 2)
            chase_bar /= swing_tendency
            chase_bar -= tunneling_bonus * 0.5
            chase_bar += sequence_penalty * 0.5
            if reaction < chase_bar:
                should_swing = True

    if batter_mods.get("force_swing") or batter_mods.get("bunt_flag"):
        should_swing = True
            
    # --- 4. RESOLVE OUTCOME ---
    
    aggressive_early = should_swing and count_snapshot == (0, 0)

    # CASE A: TAKE
    if not should_swing:
        call, flipped = _call_with_umpire_bias(state, location)
        if call == "Strike":
            description = "Looking" if location == "Zone" else "Called Strike"
            res = PitchResult(pitch.pitch_name, location, "Strike", description, velocity)
            res = _finalize_result(res)
            _maybe_mark_close_call(state, batter, res, took_pitch=True, leverage=1.6 if flipped else 1.0)
            _note_batter_behavior(
                state,
                batter_id,
                times_faced=times_through_order,
                zone_take=(location == "Zone"),
            )
            _commit_sequence_memory(state, pitcher_id, batter_id, pitch.pitch_name, p_def, location, velocity)
            _adjust_pitcher_presence(state, pitcher_id, 0.12 if location == "Zone" else 0.05)
            return res
        result = PitchResult(pitch.pitch_name, location, "Ball", "Ball", velocity)
        result = _finalize_result(result)
        _maybe_flag_wild_pitch(result, state, pitcher)
        _maybe_mark_close_call(state, pitcher, result, took_pitch=True, role="pitcher", leverage=1.6 if flipped else 1.0)
        _note_batter_behavior(
            state,
            batter_id,
            times_faced=times_through_order,
            disciplined_take=(location == "Chase"),
        )
        _commit_sequence_memory(state, pitcher_id, batter_id, pitch.pitch_name, p_def, location, velocity)
        _adjust_pitcher_presence(state, pitcher_id, -0.1)
        return result

    # CASE B: SWING
    hit_difficulty = effective_movement + mechanics_deception
    _battle_breakdown = [
        ("movement", effective_movement),
        ("deception", mechanics_deception),
    ]
    if location == "Chase":
        hit_difficulty += 30
        _battle_breakdown.append(("chase_penalty", 30))
    if velocity > 150:
        hit_difficulty += 10
        _battle_breakdown.append(("velo_bonus", 10))
    if tunneling_bonus:
        hit_difficulty += tunneling_bonus
        _battle_breakdown.append(("tunneling", tunneling_bonus))
    if sequence_penalty:
        hit_difficulty -= sequence_penalty
        _battle_breakdown.append(("sequence_relief", -sequence_penalty))
    if forced_call:
        hit_difficulty -= 5
        _battle_breakdown.append(("forced_call_relief", -5))
    
    # Pitcher Control Check (Mistake pitch?)
    mistake_pitch = rng.randint(0, 100) > effective_control
    if mistake_pitch:
        hit_difficulty -= 20 # Hanging pitch
    
    # Calculate Contact
    contact_quality = bat_control - hit_difficulty + rng.randint(0, 20)

    def _attach_battle_debug(res_obj: PitchResult):
        # Capture the key numbers used for this swing so UI can explain why it failed/succeeded.
        battle_debug = {
            "bat_control": round(bat_control, 2),
            "hit_difficulty": round(hit_difficulty, 2),
            "contact_mod": batter_mods.get("contact_mod", 0),
            "power_mod": batter_mods.get("power_mod", 0),
            "velocity": round(velocity, 2),
            "movement": round(effective_movement, 2),
            "battle_breakdown": _battle_breakdown,
        }
        res_obj.battle_debug = battle_debug

        team_id = getattr(batter, "team_id", getattr(batter, "school_id", None))
        if team_id != 1:
            return

        drivers = []
        if velocity:
            drivers.append(f"velo {velocity:.0f}")
        for label, val in _battle_breakdown:
            if label in {"chase_penalty", "tunneling", "velo_bonus"} and val:
                drivers.append(f"{label.replace('_', ' ')} {val:+.0f}")
        driver_txt = (" Drivers: " + ", ".join(drivers)) if drivers else ""
        line = (
            f"Battle math: bat control {bat_control:.0f} vs difficulty {hit_difficulty:.0f}"
            f" (contact mod {batter_mods.get('contact_mod', 0):+}).{driver_txt}"
        )

        # Always push to logs for UI consumption; optionally print if commentary is on.
        if ADV_BATTLE_FEEDBACK:
            for attr in ("at_bat_log", "play_by_play", "logs"):
                log_ref = getattr(state, attr, None)
                if isinstance(log_ref, list):
                    log_ref.append(line)
                    break
        if commentary_enabled():
            print(f"   >> {line}")
    
    if contact_quality < 0:
        res = PitchResult(pitch.pitch_name, location, "Strike", "Swinging Miss", velocity)
        _attach_battle_debug(res)
        res = _finalize_result(res)
        _note_batter_behavior(
            state,
            batter_id,
            times_faced=times_through_order,
            chase_swing=(location == "Chase"),
            late_on_heat=(velocity >= 145),
            aggressive_early=aggressive_early,
        )
        _commit_sequence_memory(state, pitcher_id, batter_id, pitch.pitch_name, p_def, location, velocity)
        _adjust_pitcher_presence(state, pitcher_id, 0.25)
        return res
    elif contact_quality < 20:
        res = PitchResult(pitch.pitch_name, location, "Foul", "Tipped", velocity)
        _attach_battle_debug(res)
        res = _finalize_result(res)
        _note_batter_behavior(
            state,
            batter_id,
            times_faced=times_through_order,
            chase_swing=(location == "Chase"),
            aggressive_early=aggressive_early,
        )
        _commit_sequence_memory(state, pitcher_id, batter_id, pitch.pitch_name, p_def, location, velocity)
        _adjust_pitcher_presence(state, pitcher_id, 0.05)
        return res
    else:
        # In Play
        res = PitchResult(pitch.pitch_name, location, "InPlay", "Contact", velocity)
        res = _finalize_result(res)
        _attach_battle_debug(res)
        
        # Attach dynamic attributes for ball_in_play logic
        res.contact_quality = contact_quality
        res.power_mod = batter_mods.get('power_mod', 0) # Pass power mod along
        if 'bunt_intent' in batter_mods:
            res.bunt_intent = batter_mods['bunt_intent']
        _note_batter_behavior(
            state,
            batter_id,
            times_faced=times_through_order,
            chase_swing=(location == "Chase"),
            hard_contact=(contact_quality >= 35 or mistake_pitch),
            aggressive_early=aggressive_early,
            clip_label="Timed that pitch" if contact_quality >= 35 else None,
        )
        _commit_sequence_memory(state, pitcher_id, batter_id, pitch.pitch_name, p_def, location, velocity)
        if contact_quality >= 35:
            _adjust_pitcher_presence(state, pitcher_id, -0.2)
        else:
            _adjust_pitcher_presence(state, pitcher_id, 0.05)
        return res