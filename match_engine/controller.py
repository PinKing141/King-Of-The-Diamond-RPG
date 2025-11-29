# match_engine/controller.py
from .pregame import prepare_match
from .inning_flow import play_inning
from .commentary import game_over
from .scoreboard import Scoreboard
from .manager_ai import manage_team_between_innings 
from database.setup_db import session, Game, Performance # Updated import path

def save_game_results(state):
    """
    Basic implementation of saving game results to DB.
    """
    # print("\nSaving Game Results...")
    g = Game(
        season_year=1, # Should pull from global state ideally
        tournament="Season Match",
        home_school_id=state.home_team.id, # FIXED: home_school_id
        away_school_id=state.away_team.id, # FIXED: away_school_id
        home_score=state.home_score, 
        away_score=state.away_score, 
        is_completed=True
    )
    session.add(g)
    session.flush()
    
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
            runs_allowed=s["runs_allowed"]
        )
        session.add(perf)
        
    session.commit()
    # print("Game Saved!")

def run_match(home_id, away_id):
    """
    Main entry point. Call this to play a full game.
    """
    # 1. Setup
    state = prepare_match(home_id, away_id)
    if not state: return None # Error handling
    
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
                print("   Match ended in a DRAW.")
                break
            else:
                print(f"   Score is tied {state.away_score}-{state.home_score}. Heading to Extra Innings!")
        
        state.inning += 1
        
    # 3. End Game
    winner = state.home_team if state.home_score > state.away_score else state.away_team
    if state.home_score == state.away_score: winner = None # Draw
    
    if winner:
        game_over(state, winner)
    
    # 4. Save
    save_game_results(state)
    
    return winner