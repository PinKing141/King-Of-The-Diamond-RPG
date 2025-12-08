import sys
from typing import Optional

from core.io_interface import IOInterface
from ui.ui_display import Colour

def player_runner_turn(runner, pitcher, state, *, io: Optional[IOInterface] = None):
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

    logger = io.log if io else print
    prompter = io.prompt if io else input

    logger(f"\n{Colour.HEADER}--- RUNNER INTERFACE ({base}) ---{Colour.RESET}")
    logger(f"Pitcher: {pitcher.name} | Catcher Arm: ???") # Could show catcher stats if scouted

    logger(f"{Colour.CYAN}Select Action:{Colour.RESET}")
    logger(" 1. STAY PUT (Safe)")
    logger(" 2. LEAD OFF (Small lead, faster jump)")
    logger(" 3. STEAL (Attempt to steal next base)")
    
    while True:
        choice = prompter("Command: ")
        if choice == '1': return "Stay"
        if choice == '2': return "Lead"
        if choice == '3': return "Steal"
        logger("Invalid command.")