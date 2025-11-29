import sys
from ui.ui_display import Colour

def player_bat_turn(pitcher, batter, state):
    """
    Handles the User Interaction for a batting turn.
    Returns: (Action String, Modifier Dictionary)
    """
    print(f"\n{Colour.HEADER}--- BATTER INTERFACE ---{Colour.RESET}")
    print(f"Pitcher: {pitcher.name} | Stamina: {getattr(pitcher, 'fatigue', 0)}% Tired")
    print(f"Count: {state.balls}-{state.strikes} | Outs: {state.outs}")
    
    # Display Options
    print(f"{Colour.CYAN}Select Approach:{Colour.RESET}")
    print(" 1. NORMAL SWING (Balanced)")
    print(" 2. POWER SWING  (High Risk, High Power)")
    print(" 3. CONTACT SWING (Bonus to hit, less Power)")
    print(" 4. TAKE PITCH   (Do not swing)")
    print(" 5. BUNT (Sacrifice for runner)")
    print(" 6. SACRIFICE FLY (Aim for outfield depth)")
    print(" 7. WAIT FOR WALK (Intentionally passive)")
    
    action = "Normal"
    mods = {}
    
    valid = False
    while not valid:
        choice = input("Command: ")
        
        if choice == '1':
            action = "Swing"
            mods = {'contact_mod': 0, 'power_mod': 0, 'eye_mod': 0}
            valid = True
            
        elif choice == '2':
            action = "Power"
            mods = {'contact_mod': -20, 'power_mod': +25, 'eye_mod': -10}
            valid = True
            
        elif choice == '3':
            action = "Contact"
            mods = {'contact_mod': +20, 'power_mod': -30, 'eye_mod': +10}
            valid = True
            
        elif choice == '4':
            action = "Take"
            mods = {} # No swing
            valid = True

        elif choice == '5':
            action = "Bunt"
            # Bunt logic: Sacrifice power completely for high contact on ground
            mods = {'contact_mod': +40, 'power_mod': -100, 'eye_mod': 0, 'bunt_flag': True}
            valid = True

        elif choice == '6':
            action = "SacFly"
            # Aim for fly ball: Moderate power, slight contact penalty
            mods = {'contact_mod': -5, 'power_mod': 0, 'eye_mod': 0, 'fly_bias': True}
            valid = True

        elif choice == '7':
            action = "Wait"
            # Boost eye significantly, penalize swing chance if forced
            mods = {'contact_mod': -50, 'power_mod': 0, 'eye_mod': +30}
            valid = True
            
        else:
            print("Invalid command.")
            
    return action, mods