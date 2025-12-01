# match_engine/manager_ai.py
from sqlalchemy.orm import Session

from database.setup_db import Player
from .commentary import commentary_enabled
from .fatigue_injury import check_pitcher_injury_risk

def find_relief_pitcher(db_session: Session, team_id, current_pitcher_id):
    """
    Finds a fresh pitcher from the roster who isn't the current one.
    """
    # Get all pitchers for the team
    pitchers = db_session.query(Player).filter_by(school_id=team_id, position='Pitcher').all()
    
    # Filter out current
    available = [p for p in pitchers if p.id != current_pitcher_id]
    
    # Filter out injured? (Assuming 'condition' or 'injury_days' > 0 check)
    available = [p for p in available if p.injury_days == 0]
    
    if not available:
        return None
        
    # Simple AI: Pick the highest rating (or random for now)
    # Ideally, pick based on stamina (if implemented)
    return max(available, key=lambda x: (x.velocity + x.control + x.stamina))

def _team_mod_types(state, team_id):
    mods = getattr(state, 'team_mods', None) or {}
    return {m['type'] for m in mods.get(team_id, [])}


def manage_team_between_innings(state, team_side):
    """
    Checks if the pitcher needs to be pulled before the inning starts.
    team_side: 'Home' or 'Away'
    """
    team = state.home_team if team_side == 'Home' else state.away_team
    pitcher = state.home_pitcher if team_side == 'Home' else state.away_pitcher
    
    p_count = state.pitch_counts.get(pitcher.id, 0)
    
    # 1. Injury Check
    is_injured, severity = check_pitcher_injury_risk(pitcher, state, state.db_session)
    if is_injured:
        if commentary_enabled():
            print(f"   🚑 MANAGER ALERT: {pitcher.last_name} is injured ({severity}) and must be pulled.")
        new_pitcher = find_relief_pitcher(state.db_session, team.id, pitcher.id)
        if new_pitcher:
            perform_pitching_change(state, team_side, new_pitcher)
        else:
            if commentary_enabled():
                print(f"   ⚠️ No relief pitchers available! {pitcher.last_name} must soldier on.")
        return

    # 2. Fatigue/Strategy Check
    # Thresholds: Stamina attribute vs Pitch Count
    stamina = getattr(pitcher, 'stamina', 50) # Default 50 if missing
    
    # Simple Logic baseline plus coach modifiers
    limit = stamina + 40
    mod_types = _team_mod_types(state, team.id)
    if 'small_ball' in mod_types:
        limit -= 10
        if commentary_enabled():
            print("   📋 Coach directive: Quick hook for pitchers (Small Ball focus).")
    if 'power_focus' in mod_types:
        limit += 10
        if commentary_enabled():
            print("   🔥 Coach directive: Let pitchers battle longer (Swing Free).")
    if p_count > limit:
        if commentary_enabled():
            print(f"   👀 MANAGER: {pitcher.last_name} looks tired (Count: {p_count}). Warming up bullpen...")
        new_pitcher = find_relief_pitcher(state.db_session, team.id, pitcher.id)
        if new_pitcher:
            perform_pitching_change(state, team_side, new_pitcher)

def perform_pitching_change(state, team_side, new_pitcher):
    if team_side == 'Home':
        if commentary_enabled():
            print(f"   🔄 PITCHING CHANGE (Home): {state.home_pitcher.last_name} -> {new_pitcher.last_name}")
        state.home_pitcher = new_pitcher
    else:
        if commentary_enabled():
            print(f"   🔄 PITCHING CHANGE (Away): {state.away_pitcher.last_name} -> {new_pitcher.last_name}")
        state.away_pitcher = new_pitcher
    
    # Reset any specific state if needed, but pitch counts for new pitcher start at 0 (or get from existing if reused)
    # The state.pitch_counts dict handles this automatically by ID.