# match_engine/controller.py
from .pregame import prepare_match
from .inning_flow import play_inning
from .commentary import commentary_enabled, game_over, set_commentary_enabled
from .scoreboard import Scoreboard
from .manager_ai import manage_team_between_innings 
from .confidence import get_confidence_summary
from database.setup_db import get_session, Game, Performance, ensure_game_schema # Updated import path
from game.personality_effects import evaluate_postgame_slumps
from game.relationship_manager import apply_confidence_relationships

def save_game_results(state):
    """
    Basic implementation of saving game results to DB.
    """
    # print("\nSaving Game Results...")
    ensure_game_schema()
    weather = getattr(state, 'weather', None)
    umpire = getattr(state, 'umpire', None)
    tilt = getattr(state, 'umpire_call_tilt', {}) or {}
    home_id = getattr(state.home_team, 'id', None)
    away_id = getattr(state.away_team, 'id', None)
    home_tilt = tilt.get(home_id, {"favored": 0, "squeezed": 0})
    away_tilt = tilt.get(away_id, {"favored": 0, "squeezed": 0})
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
        umpire_name=getattr(umpire, 'name', None),
        umpire_description=getattr(umpire, 'description', None),
        umpire_zone_bias=getattr(umpire, 'zone_bias', None),
        umpire_home_bias=getattr(umpire, 'home_bias', None),
        umpire_temperament=getattr(umpire, 'temperament', None),
        umpire_favored_home=home_tilt.get('favored', 0),
        umpire_squeezed_home=home_tilt.get('squeezed', 0),
        umpire_favored_away=away_tilt.get('favored', 0),
        umpire_squeezed_away=away_tilt.get('squeezed', 0),
    )
    db_session = state.db_session
    if db_session is None:
        raise ValueError("MatchState missing db_session for persistence.")

    db_session.add(g)
    db_session.flush()
    
    # Save Player Stats
    for p_id, s in state.stats.items():
        team_id = state.player_team_map.get(p_id)
        if team_id is None:
            is_home = any(p.id == p_id for p in state.home_roster if p) or getattr(state.home_pitcher, 'id', None) == p_id
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


def _print_lineup_card(state):
    if not commentary_enabled():
        return

    def _format_row(idx, player):
        name = getattr(player, 'name', None) or getattr(player, 'last_name', 'Player')
        pos = getattr(player, 'position', '??')
        labels = state.get_player_milestone_labels(getattr(player, 'id', None))
        tag = f" [{' / '.join(labels)}]" if labels else ""
        return f"  {idx}. {name} ({pos}){tag}"

    print("\n=== LINEUP CARD ===")
    print(f"{state.away_team.name.upper()} (Away)")
    for idx, player in enumerate(state.away_lineup[:9], start=1):
        print(_format_row(idx, player))
    print(f"\n{state.home_team.name.upper()} (Home)")
    for idx, player in enumerate(state.home_lineup[:9], start=1):
        print(_format_row(idx, player))
    print("===================\n")

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
        _print_lineup_card(state)
        
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

            # Make sure downstream callers can inspect winner attributes after
            # this function closes the session.
            try:
                db_session.refresh(winner)
                db_session.expunge(winner)
            except Exception:
                pass
        
        return winner
    finally:
        set_commentary_enabled(previous_commentary)
        db_session.close()