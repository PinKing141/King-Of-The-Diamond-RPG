import sys
from ui.ui_display import Colour
from match_engine.pitch_logic import get_arsenal, PitchResult, describe_batter_tells

def player_pitch_turn(pitcher, batter, state):
    """
    Handles the User Interaction for a pitching turn.
    Returns: (PitchRepertoire Object, Location String)
    """
    print(f"\n{Colour.HEADER}--- PITCHER INTERFACE ---{Colour.RESET}")
    print(f"vs {batter.name} (Pow {batter.power} / Con {batter.contact})")
    print(f"Count: {state.balls}-{state.strikes} | Outs: {state.outs}")
    hints = describe_batter_tells(state, batter)
    if hints:
        print(f"Intel: {' | '.join(hints)}")
    
    # Check runners for pickoff context
    has_runners = any(r is not None for r in state.runners)

    # 1. Get Arsenal
    arsenal = get_arsenal(pitcher.id)
    
    # 2. Display Options
    print(f"{Colour.CYAN}Select Pitch:{Colour.RESET}")
    for idx, pitch in enumerate(arsenal):
        print(f" {idx+1}. {pitch.pitch_name} (Qual: {pitch.quality})")
    
    if has_runners:
        print(f" {len(arsenal)+1}. PICKOFF ATTEMPT")
        print(f" {len(arsenal)+2}. PITCH OUT")

    # 3. Input Loop for Pitch/Action
    selected_pitch = None
    special_action = None

    while not selected_pitch and not special_action:
        try:
            choice = input(f"Command (1-{len(arsenal) + (2 if has_runners else 0)}): ")
            idx = int(choice) - 1
            
            if 0 <= idx < len(arsenal):
                selected_pitch = arsenal[idx]
            elif has_runners and idx == len(arsenal):
                return None, "Pickoff" # Special return
            elif has_runners and idx == len(arsenal) + 1:
                return None, "PitchOut" # Special return
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a number.")

    # 4. Input Loop for Location (Only if pitching normally)
    print(f"\n{Colour.CYAN}Select Location:{Colour.RESET}")
    print(" 1. ZONE (Standard)")
    print(" 2. CHASE (Edge/Ball - Harder to hit, might walk)")
    
    location = "Zone"
    valid_loc = False
    while not valid_loc:
        choice = input("Target (1-2): ")
        if choice == '1':
            location = "Zone"
            valid_loc = True
        elif choice == '2':
            location = "Chase"
            valid_loc = True
        else:
            print("Invalid target.")

    print(f" > Throwing {selected_pitch.pitch_name} to {location}...")
    return selected_pitch, location