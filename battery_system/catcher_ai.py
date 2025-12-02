# battery_system/catcher_ai.py
import random
from match_engine.pitch_logic import get_arsenal, get_last_pitch_call
from match_engine.pitch_definitions import PITCH_TYPES

def suggest_pitch_logic(catcher, pitcher, batter, state, exclude_pitch_name=None):
    """
    AI Catcher logic to decide what pitch to call.
    Returns: (PitchRepertoire, Location, Intent)
    """
    arsenal = get_arsenal(pitcher.id)
    if not arsenal:
        return None, "Zone", "Normal"
    if exclude_pitch_name:
        filtered = [p for p in arsenal if p.pitch_name != exclude_pitch_name]
        if filtered:
            arsenal = filtered
    
    # 1. Analyze Count
    is_ahead = state.strikes > state.balls
    is_behind = state.balls > state.strikes
    two_strikes = state.strikes == 2
    batter_id = getattr(batter, 'id', None)
    pitcher_id = getattr(pitcher, 'id', None)
    times_seen = getattr(state, 'times_through_order', {}).get(pitcher_id, {}).get(batter_id, 1)
    intel = getattr(state, 'batter_tell_tracker', {}).get(batter_id, {})
    last_call = get_last_pitch_call(state, pitcher_id, batter_id)
    
    def _family(pitch_obj):
        return PITCH_TYPES.get(pitch_obj.pitch_name, {}).get('family', 'Fastball')
    
    # 2. Pick Pitch based on Arsenal Quality & Situation
    best_pitch = max(arsenal, key=lambda x: x.quality)
    candidate_pool = list(arsenal)

    if last_call and times_seen >= 3:
        varied = [p for p in candidate_pool if _family(p) != last_call.get('family')]
        if varied:
            candidate_pool = varied

    if last_call and times_seen >= 2:
        different_shape = [p for p in candidate_pool if p.pitch_name != last_call.get('pitch_name')]
        if different_shape:
            candidate_pool = different_shape

    selected_pitch = best_pitch
    location = "Zone"

    if two_strikes:
        breakers = [p for p in candidate_pool if _family(p) in {"Breaker", "Changeup", "Splitter"}]
        if breakers:
            selected_pitch = random.choice(breakers)
            location = "Chase"
        else:
            selected_pitch = best_pitch
            location = "Chase"
    elif is_behind:
        fastballs = [p for p in candidate_pool if _family(p) == "Fastball"]
        if fastballs:
            selected_pitch = fastballs[0]
        location = "Zone"
    else:
        selected_pitch = random.choice(candidate_pool)

    if intel.get('chase_swings', 0) >= 2 and not is_behind:
        location = "Chase"
    if intel.get('disciplined', 0) >= 2:
        location = "Zone"

    return selected_pitch, location, "Normal"