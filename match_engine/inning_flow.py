# match_engine/inning_flow.py
from .batter_logic import start_at_bat
from .scoreboard import Scoreboard

def rotate_lineup(lineup):
    """Moves the first batter to the end of the list."""
    return lineup[1:] + lineup[:1]

def play_inning(state, scoreboard):
    """
    Plays both Top and Bottom of an inning.
    """
    
    # --- TOP (Away Team) ---
    state.top_bottom = "Top"
    state.outs = 0
    state.clear_bases()
    start_runs_away = state.away_score
    
    print(f"\n--- TOP OF INNING {state.inning} ---")
    while state.outs < 3:
        start_at_bat(state)
        # Rotate Away Lineup
        state.away_lineup = rotate_lineup(state.away_lineup)
        
        # Mercy Rule Check or Game End Check could go here
    
    runs_scored_top = state.away_score - start_runs_away
    
    # Check if Home team wins without playing bottom (9th inning walkoff logic is in bottom)
    if state.inning >= 9 and state.home_score > state.away_score:
        scoreboard.record_inning(state.inning, runs_scored_top, None) # X for bottom
        return # Game Over
        
    # --- BOTTOM (Home Team) ---
    state.top_bottom = "Bot"
    state.outs = 0
    state.clear_bases()
    start_runs_home = state.home_score
    
    print(f"\n--- BOTTOM OF INNING {state.inning} ---")
    while state.outs < 3:
        start_at_bat(state)
        # Rotate Home Lineup
        state.home_lineup = rotate_lineup(state.home_lineup)
        
        # Walk-off check
        if state.inning >= 9 and state.home_score > state.away_score:
            print(f"\n   >>> WALK-OFF WIN FOR {state.home_team.school_name}! <<<")
            state.outs = 3 # Break loop
            break

    runs_scored_bot = state.home_score - start_runs_home
    scoreboard.record_inning(state.inning, runs_scored_top, runs_scored_bot)
    
    scoreboard.print_board(state)