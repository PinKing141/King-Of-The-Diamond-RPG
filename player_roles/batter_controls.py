import sys
from ui.ui_display import Colour


_BATTERS_EYE_CHOICES = {
    '1': {"kind": "family", "value": "fastball", "label": "Fastball"},
    '2': {"kind": "family", "value": "breaker", "label": "Breaking Ball"},
    '3': {"kind": "family", "value": "offspeed", "label": "Offspeed (Change/Split)"},
    '4': {"kind": "location", "value": "zone", "label": "In the Zone"},
    '5': {"kind": "location", "value": "chase", "label": "Out of Zone"},
}


def _prompt_batters_eye() -> dict | None:
    """Optional pre-pitch guess that fuels the Batter's Eye mechanic."""
    print(f"\n{Colour.GOLD}Batter's Eye — Sit on something?{Colour.RESET}")
    print(" Enter to skip if you want to stay reactive.")
    print(" 1. Fastball family")
    print(" 2. Breaking ball")
    print(" 3. Offspeed / Splitter")
    print(" 4. Zone attack (strike)")
    print(" 5. Waste pitch (outside zone)")
    while True:
        choice = input("Sit on: ").strip().lower()
        if choice in {"", "0", "skip"}:
            return None
        payload = _BATTERS_EYE_CHOICES.get(choice)
        if payload:
            print(f" Locking in on {payload['label']}.")
            data = payload.copy()
            data['source'] = 'user'
            return data
        print(" Invalid guess. Enter 1-5 or press Enter to skip.")

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
            
    guess_payload = _prompt_batters_eye()
    if guess_payload:
        mods['guess_payload'] = guess_payload
    return action, mods