# battery_system/battery_negotiation.py
import time
from ui.ui_display import Colour
from match_engine.pitch_logic import get_arsenal
from .battery_trust import get_trust
from .pitcher_personality import does_pitcher_accept
from .catcher_ai import suggest_pitch_logic


def _player_team_id(player):
    return getattr(player, 'team_id', getattr(player, 'school_id', None))

def run_battery_negotiation(pitcher, catcher, batter, state):
    """
    The Pre-Pitch Loop.
    Exchange signs until an agreement is reached or limit exceeded.
    Returns: (Pitch, Location) to be passed to resolve_pitch.
    """
    
    # 1. Identify Roles
    user_is_pitcher = (_player_team_id(pitcher) == 1) # User controls Pitcher
    user_is_catcher = (_player_team_id(catcher) == 1) # User controls Catcher (Future feature)
    
    # For now, we assume User is Pitcher OR User watches AI vs AI.
    # If User is Catcher (Phase 5), we'd swap the logic.
    
    trust = get_trust(pitcher.id, catcher.id)
    
    # AI Catcher generates initial suggestion
    suggestion, location, intent = suggest_pitch_logic(catcher, pitcher, batter, state)
    
    # --- NEGOTIATION LOOP ---
    max_shake_offs = 3
    shakes = 0
    
    while shakes < max_shake_offs:
        
        # Display the Sign (if User is Pitcher or watching)
        if user_is_pitcher:
            print(f"\n{Colour.BLUE}[Catcher Sign] {suggestion.pitch_name} ({location}){Colour.RESET}")
            print(f"   (Trust: {trust} | Shakes left: {max_shake_offs - shakes})")
            
            # User Decision
            print("   1. Accept Sign")
            print("   2. Shake Off")
            choice = input("   >> ")
            
            if choice == '1':
                return suggestion, location # AGREEMENT
            else:
                shakes += 1
                print("   (Shaking off...)")
                # AI Catcher picks a DIFFERENT pitch
                arsenal = get_arsenal(pitcher.id)
                new_options = [p for p in arsenal if p.id != suggestion.id]
                if new_options:
                    suggestion = new_options[0] # Simply rotate to next option
                    # Or random choice from remaining
                else:
                    # No other pitches? Re-suggest same with different location?
                    location = "Chase" if location == "Zone" else "Zone"
                    
        else:
            # AI Pitcher Decision
            if does_pitcher_accept(pitcher, suggestion, trust):
                # print(f"   (P) {pitcher.last_name} nods.")
                return suggestion, location
            else:
                shakes += 1
                # print(f"   (P) {pitcher.last_name} shakes off sign.")
                # Logic to rotate pitch similar to above
                arsenal = get_arsenal(pitcher.id)
                new_options = [p for p in arsenal if p.id != suggestion.id]
                if new_options:
                    suggestion = new_options[0]
                else:
                    location = "Chase" if location == "Zone" else "Zone"

    # If loop ends, Pitcher MUST throw the last suggestion (or auto-select fastball)
    # print("   (Catcher visits mound: 'Just throw the heat!')")
    return suggestion, location