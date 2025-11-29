import sys
import os
from sqlalchemy.orm import sessionmaker
from database.setup_db import Game, engine
# Import the actual logic from your new controller
from .controller import run_match as engine_run_match

Session = sessionmaker(bind=engine)

class SuppressPrint:
    """
    Context manager to silence output. 
    Used when simulations run background matches.
    """
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout

def sim_match(home_team, away_team, tournament_name="Practice Match", silent=False):
    """
    BRIDGE FUNCTION (Now inside match_engine/)
    ----------------
    Old code calls this function expecting a match result.
    This function forwards the request to the new 'match_engine.controller'.
    """
    winner = None
    
    # 1. Run the Match (Silent or Loud)
    if silent:
        with SuppressPrint():
            # This runs the full new engine but hides the commentary
            winner = engine_run_match(home_team.id, away_team.id)
    else:
        # Runs with full commentary visible
        winner = engine_run_match(home_team.id, away_team.id)
    
    # 2. Retrieve Score (For backward compatibility)
    # The new engine saves to DB, so we look up what just happened.
    session = Session()
    try:
        # Find the most recent game between these two teams
        game = session.query(Game).filter(
            Game.home_school_id == home_team.id, # Fixed: V2 uses home_school_id
            Game.away_school_id == away_team.id  # Fixed: V2 uses away_school_id
        ).order_by(Game.id.desc()).first()
        
        score_str = "0 - 0"
        if game:
            score_str = f"{game.away_score} - {game.home_score}"
            
            # Update the tournament name tag
            if tournament_name != "Practice Match":
                game.tournament = tournament_name
                session.commit()
                
    except Exception as e:
        print(f"Error retrieving match result: {e}")
        score_str = "Error"
    finally:
        session.close()

    return winner, score_str