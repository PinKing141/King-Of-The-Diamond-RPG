# battery_system/catcher_ai.py
import random
from match_engine.pitch_logic import get_arsenal

def suggest_pitch_logic(catcher, pitcher, batter, state):
    """
    AI Catcher logic to decide what pitch to call.
    Returns: (PitchRepertoire, Location, Intent)
    """
    arsenal = get_arsenal(pitcher.id)
    if not arsenal: return None, "Zone", "Normal"
    
    # 1. Analyze Count
    is_ahead = state.strikes > state.balls
    is_behind = state.balls > state.strikes
    two_strikes = state.strikes == 2
    
    # 2. Pick Pitch based on Arsenal Quality & Situation
    # Sort arsenal by quality
    best_pitch = max(arsenal, key=lambda x: x.quality)
    
    selected_pitch = best_pitch
    location = "Zone"
    
    if two_strikes:
        # Try to finish them off
        breakers = [p for p in arsenal if "Fastball" not in p.pitch_name]
        if breakers:
            selected_pitch = random.choice(breakers)
            location = "Chase"
        else:
            selected_pitch = best_pitch
            location = "Chase" # High heat chase?
            
    elif is_behind:
        # Need a strike. Go with best control or fastball.
        fastballs = [p for p in arsenal if "Fastball" in p.pitch_name]
        if fastballs:
            selected_pitch = fastballs[0]
        location = "Zone"
        
    else:
        # Mix it up
        selected_pitch = random.choice(arsenal)
        location = "Zone"

    return selected_pitch, location, "Normal"