import time
from .pitch_logic import resolve_pitch
from .ball_in_play import resolve_contact
from .base_running import advance_runners
from .commentary import display_state, announce_pitch, announce_play, announce_score_change

def start_at_bat(state):
    """
    Simulates one complete At-Bat.
    Returns True if the inning continues, False if 3 outs reached immediately.
    """
    pitcher = state.home_pitcher if state.top_bottom == "Top" else state.away_pitcher
    batter = state.away_lineup[0] if state.top_bottom == "Top" else state.home_lineup[0]
    batting_team = state.away_team if state.top_bottom == "Top" else state.home_team
    
    state.reset_count()
    display_state(state, pitcher, batter)
    
    while True:
        # time.sleep(0.5) # Pace the game
        
        # --- USER INPUT CHECK (BATTER) ---
        batter_action = "Normal"
        batter_mods = {}
        
        # Check if Batter is USER (Assuming Team ID 1 is User)
        if batter.team_id == 1:
             from player_roles.batter_controls import player_bat_turn
             batter_action, batter_mods = player_bat_turn(pitcher, batter, state)
        
        # 1. Pitch Resolution (Pass batter intent)
        state.add_pitch_count(pitcher.id)
        pitch_res = resolve_pitch(pitcher, batter, state, batter_action, batter_mods)
        
        announce_pitch(pitch_res)
        
        # 2. Update Count
        if pitch_res.outcome == "Ball":
            state.balls += 1
            if state.balls == 4:
                print("   >> WALK.")
                state.runners[0] = batter 
                state.stats[batter.id]["walks"] += 1
                state.stats[pitcher.id]["walks"] += 1
                break
                
        elif pitch_res.outcome == "Strike":
            if state.strikes < 2 or pitch_res.description != "Foul": 
                state.strikes += 1
            
            if state.strikes == 3:
                print("   >> STRIKEOUT!")
                state.outs += 1
                state.stats[batter.id]["strikeouts"] += 1
                state.stats[pitcher.id]["strikeouts_pitched"] += 1
                break
                
        elif pitch_res.outcome == "Foul":
            if state.strikes < 2:
                state.strikes += 1
                
        elif pitch_res.outcome == "InPlay":
            # 3. Contact
            # Note: resolve_contact might need to know about Power Swing mods?
            # For now, we assume pitch_res.contact_quality handles the 'Hit' probability,
            # but we might want to pass power_mod to resolve_contact for distance.
            
            # Extract power mod if it was attached in pitch_logic
            p_mod = getattr(pitch_res, 'power_mod', 0)
            
            contact_res = resolve_contact(pitch_res.contact_quality, batter, pitcher, power_mod=p_mod)
            announce_play(contact_res)
            
            if contact_res.hit_type == "Out":
                state.outs += 1
                state.stats[batter.id]["at_bats"] += 1
                state.stats[pitcher.id]["innings_pitched"] += 0.33
            else:
                # HIT!
                state.stats[batter.id]["hits"] += 1
                state.stats[batter.id]["at_bats"] += 1
                if contact_res.hit_type == "HR": state.stats[batter.id]["homeruns"] += 1
                
                # Move Runners
                runs = advance_runners(state, contact_res.hit_type, batter)
                
                if runs > 0:
                    announce_score_change(runs, batting_team.school_name)
                    if state.top_bottom == "Top": state.away_score += runs
                    else: state.home_score += runs
                    
                    state.stats[batter.id]["rbi"] += runs
                    state.stats[pitcher.id]["runs_allowed"] += runs
            
            break # At bat over

    return