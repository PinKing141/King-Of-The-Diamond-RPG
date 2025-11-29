import sys
from ui.ui_display import Colour

def player_runner_turn(runner, pitcher, state):
    """
    Handles User Interaction when the player is on base.
    Returns: Action String
    """
    # Identify which base the user is on
    base = ""
    if state.runners[0] and state.runners[0].id == runner.id: base = "1st"
    elif state.runners[1] and state.runners[1].id == runner.id: base = "2nd"
    elif state.runners[2] and state.runners[2].id == runner.id: base = "3rd"
    
    if not base: return "Stay" # Should not happen if called correctly

    print(f"\n{Colour.HEADER}--- RUNNER INTERFACE ({base}) ---{Colour.RESET}")
    print(f"Pitcher: {pitcher.name} | Catcher Arm: ???") # Could show catcher stats if scouted
    
    print(f"{Colour.CYAN}Select Action:{Colour.RESET}")
    print(" 1. STAY PUT (Safe)")
    print(" 2. LEAD OFF (Small lead, faster jump)")
    print(" 3. STEAL (Attempt to steal next base)")
    
    while True:
        choice = input("Command: ")
        if choice == '1': return "Stay"
        if choice == '2': return "Lead"
        if choice == '3': return "Steal"
        print("Invalid command.")