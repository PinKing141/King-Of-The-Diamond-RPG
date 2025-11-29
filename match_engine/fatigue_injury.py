# match_engine/fatigue_injury.py
import random
from database.setup_db import session, engine
from game.health_system import apply_injury

# Connect to raw connection for the existing health_system logic if needed,
# or use the session we have.
conn = engine.raw_connection()

def check_pitcher_injury_risk(pitcher, state):
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
        
    if random.random() < base_risk:
        # INJURY OCCURRED
        roll = random.random()
        severity = "Minor"
        if roll > 0.90: severity = "Severe"
        elif roll > 0.70: severity = "Moderate"
        
        # Apply to DB
        msg = apply_injury(conn, severity) # Uses your existing health system
        
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
    
    return {"velocity": velocity_drop, "control": control_drop}