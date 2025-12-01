# match_engine/fatigue_injury.py
from typing import Dict, Optional

from sqlalchemy.orm import Session

from game.health_system import apply_injury
from game.rng import get_rng
from game.skill_system import gather_roll_modifiers
from match_engine.context_manager import get_at_bat_context

rng = get_rng()


def check_pitcher_injury_risk(pitcher, state, db_session: Session):
    """
    Evaluates if a pitcher suffers an injury based on pitch count and current stamina.
    Returns (bool, str): (is_injured, severity_msg)
    """
    p_count = state.pitch_counts.get(pitcher.id, 0)
    
    # Safe zone
    if p_count < 80:
        return False, None

    # Risk Calculation
    # e.g., 100 pitches = (100-80) * 0.05% = 1% chance per batter faced? 
    # Let's keep it low but dangerous for high counts.
    base_risk = (p_count - 80) * 0.0005 
    
    if p_count > 110:
        base_risk += 0.02 # Spike in risk

    roll_context = _build_roll_context(state, pitcher)
    roll_mods = gather_roll_modifiers(pitcher, roll_context)

    drive = getattr(pitcher, "drive", 50) or 50
    volatility = getattr(pitcher, "volatility", 50) or 50
    ambition_push = max(0.0, (drive - 65) / 35.0)
    pressure_bonus = _volatility_pressure_push(volatility, state)

    if p_count > 100:
        base_risk *= 1 + ambition_push * 0.6
    base_risk *= 1 + pressure_bonus * 0.5

    injury_scale = max(0.1, 1.0 + float(roll_mods.get("injury", 0.0))) if roll_mods else 1.0
    base_risk *= injury_scale
        
    if rng.random() < base_risk:
        # INJURY OCCURRED
        roll = rng.random()
        severity = "Minor"
        if roll > 0.90: severity = "Severe"
        elif roll > 0.70: severity = "Moderate"
        
        # Apply to DB
        msg = apply_injury(db_session, severity, pitcher)
        
        # Log it in the match state
        state.log(f"INJURY: {pitcher.last_name} injured! ({severity})")
        
        return True, severity
        
    return False, None

def get_fatigue_status(pitcher, state):
    """
    Returns a dictionary of penalties to apply to the pitch physics.
    """
    p_count = state.pitch_counts.get(pitcher.id, 0)
    
    velocity_drop = 0
    control_drop = 0
    
    if p_count > 80: velocity_drop = (p_count - 80) * 0.2
    if p_count > 100: velocity_drop += (p_count - 100) * 0.5
    
    if p_count > 90: control_drop = (p_count - 90) * 0.5

    roll_context = _build_roll_context(state, pitcher)
    roll_mods = gather_roll_modifiers(pitcher, roll_context)

    fatigue_scale = _fatigue_scale(pitcher, state, roll_mods)
    velocity_drop *= fatigue_scale
    control_drop *= fatigue_scale
    
    return {"velocity": velocity_drop, "control": control_drop}


def _fatigue_scale(pitcher, state, roll_mods: Optional[Dict[str, float]] = None) -> float:
    drive = getattr(pitcher, "drive", 50) or 50
    ambition = getattr(pitcher, "ambition", drive) or 50
    volatility = getattr(pitcher, "volatility", 50) or 50

    drive_relief = max(0.0, (drive - 60) / 45.0)
    ambition_relief = max(0.0, (ambition - 55) / 35.0)
    pressure_push = _volatility_pressure_push(volatility, state)

    pressure_scale = 0.35 if _is_pressure_cooker(state) else 0.20
    volatility_penalty = pressure_push * (0.35 + pressure_scale)

    scale = 1.0 - (drive_relief * 0.20) - (ambition_relief * 0.45) + volatility_penalty
    if roll_mods:
        fatigue_scale = max(0.1, 1.0 + float(roll_mods.get("fatigue", 0.0)))
        scale *= fatigue_scale
    return max(0.35, min(1.75, scale))


def _volatility_pressure_push(volatility: int, state) -> float:
    if not _is_pressure_cooker(state):
        return max(0.0, (volatility - 65) / 60.0)
    return max(0.0, (volatility - 50) / 40.0)


def _is_pressure_cooker(state) -> bool:
    inning = getattr(state, "inning", 1)
    score_gap = abs((state.home_score or 0) - (state.away_score or 0))
    runners = getattr(state, "runners", None)
    runners_in_scoring_pos = any(runners[1:]) if runners else False
    late = inning >= 7
    return (late and score_gap <= 2) or runners_in_scoring_pos


def _build_roll_context(state, pitcher) -> Dict[str, object]:
    try:
        return get_at_bat_context(state, getattr(state, "current_batter", None), pitcher)
    except Exception:
        return {
            "inning": getattr(state, "inning", 1),
            "pressure_state": "high" if _is_pressure_cooker(state) else "normal",
        }