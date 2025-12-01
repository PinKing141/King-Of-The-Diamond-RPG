from database.setup_db import PitchRepertoire, session_scope
from match_engine.pitch_definitions import PITCH_TYPES, ARM_SLOT_MODIFIERS
from game.rng import get_rng
from game.skill_system import player_has_skill

rng = get_rng()


def _player_team_id(player):
    return getattr(player, 'team_id', getattr(player, 'school_id', None))


def _offense_team_id(state):
    return getattr(state.away_team, 'id', None) if getattr(state, 'top_bottom', 'Top') == 'Top' else getattr(state.home_team, 'id', None)


def _defense_team_id(state):
    return getattr(state.home_team, 'id', None) if getattr(state, 'top_bottom', 'Top') == 'Top' else getattr(state.away_team, 'id', None)


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


class PitchResult:
    def __init__(self, pitch_name, location, outcome, description, velocity=0):
        self.pitch_name = pitch_name
        self.location = location  # "Zone" or "Chase"
        self.outcome = outcome  # "Ball", "Strike", "Foul", "InPlay"
        self.description = description  # "Swinging Miss", "Looking", "Weak Grounder"
        self.velocity = velocity
        self.contact_quality = 0  # Default
        self.special = None
        self.argument_penalty = 0
        self.argument_target_id = None
        self.argument_ejection = False


def _maybe_flag_wild_pitch(result, state, pitcher):
    weather = getattr(state, 'weather', None)
    if result.outcome != "Ball" or not any(state.runners):
        return
    control = getattr(pitcher, 'control', 50) or 50
    fatigue = max(0, state.pitch_counts.get(pitcher.id, 0) - 85)
    weather_push = getattr(weather, 'wild_pitch_modifier', 0.0) if weather else 0.0
    base = max(0.0, (60 - control) * 0.0025)
    fatigue_bonus = fatigue * 0.001
    chance = base + fatigue_bonus
    if weather_push >= 0:
        chance += weather_push * 1.2
    else:
        chance += weather_push * 0.6
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


def _call_with_umpire_bias(state, location: str) -> tuple[str, bool]:
    """Return the called outcome (Strike/Ball) and whether it defied the default zone."""
    default = "Strike" if location == "Zone" else "Ball"
    umpire = getattr(state, "umpire", None)
    if not umpire:
        return default, False
    pitcher_is_home = getattr(state, "top_bottom", "Top") == "Top"
    zone_bias = getattr(umpire, "zone_bias", 0.0) or 0.0
    home_bias = getattr(umpire, "home_bias", 0.0) or 0.0
    temperament = getattr(umpire, "temperament", 0.5) or 0.5
    mood = getattr(state, "umpire_mood", 0.0) or 0.0

    base = 1.3 if location == "Zone" else -1.3
    base -= zone_bias
    if home_bias:
        base += home_bias if pitcher_is_home else -home_bias
    base += mood
    swing = 0.25 + temperament * 0.2
    base += rng.uniform(-swing, swing)
    call = "Strike" if base >= 0 else "Ball"
    flipped = call != default
    # drift mood slightly toward neutrality unless challenged again
    if flipped:
        favored_role = "defense" if call == "Strike" else "offense"
        _record_umpire_bias(state, favored_role)
        drift = -0.05 if call == "Strike" else 0.07
        _adjust_umpire_mood(state, drift)
    else:
        _adjust_umpire_mood(state, mood * -0.15)
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

    from match_engine.confidence import get_confidence

    # --- 1. PITCH SELECTION (BATTERY NEGOTIATION) ---
    pitch = None
    location = "Zone"

    # Identify the Catcher
    catcher = get_current_catcher(state)

    # Use the Battery System to negotiate the sign
    # Import inside function to avoid circular dependency
    from battery_system.battery_negotiation import run_battery_negotiation
    
    if catcher:
        pitch, location = run_battery_negotiation(pitcher, catcher, batter, state)
    else:
        # Fallback if no catcher found (shouldn't happen in real game)
        from player_roles.pitcher_controls import player_pitch_turn
        pitch, location = player_pitch_turn(pitcher, batter, state)

    # --- 2. PITCH PHYSICS ---
    p_def = PITCH_TYPES.get(pitch.pitch_name, PITCH_TYPES["4-Seam Fastball"])
    
    # Arm Slot Mods
    arm_slot = getattr(pitcher, 'arm_slot', 'Overhand')
    slot_mods = ARM_SLOT_MODIFIERS.get(arm_slot, ARM_SLOT_MODIFIERS["Overhand"])
    
    # Fatigue Calculation
    p_count = state.pitch_counts.get(pitcher.id, 0)
    fatigue_penalty = 0
    control_penalty = 0
    
    if p_count > 80: fatigue_penalty = (p_count - 80) * 0.2
    if p_count > 100: fatigue_penalty += (p_count - 100) * 0.5
    if p_count > 90: control_penalty = (p_count - 90) * 0.5
    
    weather = getattr(state, 'weather', None)

    # Final Values
    base_velocity = (getattr(pitcher, 'velocity', 0) or 0) + pitcher_trait_mods.get('velocity', 0)
    velocity = (base_velocity * p_def['velocity_mod']) - fatigue_penalty
    base_movement = pitch.break_level * p_def['break_mod']
    
    if p_def['type'] in ["Vertical", "Drop_Sink"]:
        effective_movement = base_movement * slot_mods['vertical_mult']
    elif p_def['type'] == "Horizontal":
        effective_movement = base_movement * slot_mods['horizontal_mult']
    else:
        effective_movement = base_movement

    base_control = (getattr(pitcher, 'control', 50) or 50) + pitcher_trait_mods.get('control', 0)
    effective_control = (base_control * slot_mods['control_penalty_mult']) - control_penalty
    if weather:
        effective_control -= weather.wild_pitch_modifier * 60
    pitch_confidence = get_confidence(state, pitcher.id)
    effective_control += pitch_confidence * 0.25
    velocity += pitch_confidence * 0.05

    # --- 3. BATTER REACTION ---
    
    # Apply mods (from User Choice or AI buffs)
    base_eye = getattr(batter, 'eye', getattr(batter, 'discipline', 50)) or 50
    base_eye += batter_trait_mods.get('discipline', 0) + batter_trait_mods.get('eye', 0)
    eye_stat = base_eye + batter_mods.get('eye_mod', 0)
    base_contact = getattr(batter, 'contact', 50) or 50
    base_contact += batter_trait_mods.get('contact', 0)
    contact_stat = base_contact + batter_mods.get('contact_mod', 0)

    if player_has_skill(batter, "clutch_hitter") and _is_clutch_situation(state):
        contact_stat *= 1.1
        batter_mods['power_mod'] = batter_mods.get('power_mod', 0) + 5
    
    reaction = eye_stat + rng.randint(-10, 10)
    bat_control = contact_stat + rng.randint(-15, 15)
    batter_conf = get_confidence(state, batter.id)
    reaction += batter_conf * 0.2
    bat_control += batter_conf * 0.3
    
    # DECISION: SWING OR TAKE?
    should_swing = False
    
    swing_tendency = max(0.5, min(2.0, batter_tendencies.get('swing_aggression', 1.0)))
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
            if reaction < chase_bar:
                should_swing = True
            
    # --- 4. RESOLVE OUTCOME ---
    
    # CASE A: TAKE
    if not should_swing:
        call, flipped = _call_with_umpire_bias(state, location)
        if call == "Strike":
            description = "Looking" if location == "Zone" else "Called Strike"
            res = PitchResult(pitch.pitch_name, location, "Strike", description, velocity)
            _maybe_mark_close_call(state, batter, res, took_pitch=True, leverage=1.6 if flipped else 1.0)
            return res
        result = PitchResult(pitch.pitch_name, location, "Ball", "Ball", velocity)
        _maybe_flag_wild_pitch(result, state, pitcher)
        _maybe_mark_close_call(state, pitcher, result, took_pitch=True, role="pitcher", leverage=1.6 if flipped else 1.0)
        return result

    # CASE B: SWING
    hit_difficulty = effective_movement
    if location == "Chase": hit_difficulty += 30
    if velocity > 150: hit_difficulty += 10
    
    # Pitcher Control Check (Mistake pitch?)
    if rng.randint(0, 100) > effective_control:
        hit_difficulty -= 20 # Hanging pitch
    
    # Calculate Contact
    contact_quality = bat_control - hit_difficulty + rng.randint(0, 20)
    
    if contact_quality < 0:
        res = PitchResult(pitch.pitch_name, location, "Strike", "Swinging Miss", velocity)
        return res
    elif contact_quality < 20:
        res = PitchResult(pitch.pitch_name, location, "Foul", "Tipped", velocity)
        return res
    else:
        # In Play
        res = PitchResult(pitch.pitch_name, location, "InPlay", "Contact", velocity)
        
        # Attach dynamic attributes for ball_in_play logic
        res.contact_quality = contact_quality
        res.power_mod = batter_mods.get('power_mod', 0) # Pass power mod along
        
        return res