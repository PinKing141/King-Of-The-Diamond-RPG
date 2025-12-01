# match_engine/controller.py
from .pregame import prepare_match
from .inning_flow import play_inning
from .commentary import commentary_enabled, game_over, set_commentary_enabled
from .scoreboard import Scoreboard
from .manager_ai import manage_team_between_innings 
from .confidence import get_confidence_summary
from database.setup_db import get_session, Game, Performance # Updated import path
from game.personality_effects import evaluate_postgame_slumps
from game.relationship_manager import apply_confidence_relationships

def save_game_results(state):
    """
    Basic implementation of saving game results to DB.
    """
    # print("\nSaving Game Results...")
    weather = getattr(state, 'weather', None)
    g = Game(
        season_year=1, # Should pull from global state ideally
        tournament="Season Match",
        home_school_id=state.home_team.id, # FIXED: home_school_id
        away_school_id=state.away_team.id, # FIXED: away_school_id
        home_score=state.home_score, 
        away_score=state.away_score, 
        is_completed=True,
        weather_label=getattr(weather, 'label', None),
        weather_condition=getattr(weather, 'condition', None),
        weather_precip=getattr(weather, 'precipitation', None),
        weather_temperature_f=getattr(weather, 'temperature_f', None),
        weather_wind_speed=getattr(weather, 'wind_speed_mph', None),
        weather_wind_direction=getattr(weather, 'wind_direction', None),
        weather_summary=weather.describe() if weather else None,
    )
    db_session = state.db_session
    if db_session is None:
        raise ValueError("MatchState missing db_session for persistence.")

    db_session.add(g)
    db_session.flush()
    
    # Save Player Stats
    for p_id, s in state.stats.items():
        # Determine team_id for this player (legacy logic or school_id)
        # Performance table likely still has team_id column or needs updating?
        # V2 schema 'PlayerGameStats' uses team_id (optional helper)
        
        # Quick check: is player home or away?
        is_home = any(p.id == p_id for p in state.home_lineup) or (state.home_pitcher.id == p_id)
        team_id = state.home_team.id if is_home else state.away_team.id
        
        perf = Performance(
            game_id=g.id,
            player_id=p_id,
            team_id=team_id, # This is fine if Performance table kept team_id column as generic ID
            at_bats=s["at_bats"],
            hits=s["hits"],
            homeruns=s["homeruns"],
            rbi=s["rbi"],
            strikeouts=s["strikeouts"],
            walks=s["walks"],
            innings_pitched=s["innings_pitched"],
            strikeouts_pitched=s["strikeouts_pitched"],
            runs_allowed=s["runs_allowed"],
            confidence=state.confidence_map.get(p_id, 0)
        )
        db_session.add(perf)
        
    state.confidence_summary_snapshot = get_confidence_summary(state)
    apply_confidence_relationships(db_session, state.confidence_summary_snapshot)
    evaluate_postgame_slumps(state)
    db_session.commit()
    # print("Game Saved!")

def run_match(home_id, away_id, *, fast: bool = False):
    """
    Main entry point. Call this to play a full game.
    """
    # 1. Setup
    db_session = get_session()
    previous_commentary = commentary_enabled()
    if fast:
        set_commentary_enabled(False)
    try:
        state = prepare_match(home_id, away_id, db_session)
        if not state:
            return None # Error handling
        
        scoreboard = Scoreboard()
        
        # 2. Game Loop
        while state.inning <= 9:
            # --- AI CHECKS ---
            manage_team_between_innings(state, 'Home')
            manage_team_between_innings(state, 'Away')
            
            play_inning(state, scoreboard)
            
            # Tie-breaker / Extra Innings logic
            if state.inning >= 9:
                if state.home_score != state.away_score:
                    break
                elif state.inning >= 12: # Draw limit
                    if commentary_enabled():
                        print("   Match ended in a DRAW.")
                    break
                else:
                    if commentary_enabled():
                        print(f"   Score is tied {state.away_score}-{state.home_score}. Heading to Extra Innings!")
            
            state.inning += 1
            
        # 3. End Game
        winner = state.home_team if state.home_score > state.away_score else state.away_team
        if state.home_score == state.away_score:
            winner = None # Draw
        
        if winner:
            game_over(state, winner)
        
        # 4. Save
            save_game_results(state)
        
        return winner
    finally:
        set_commentary_enabled(previous_commentary)
        db_session.close()