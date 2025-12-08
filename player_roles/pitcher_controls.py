import sys
from typing import Optional

from core.io_interface import IOInterface
from ui.ui_display import Colour
from match_engine.pitch_logic import get_arsenal, PitchResult, describe_batter_tells

SLIDE_STEP_MODES = ("auto", "force_on", "force_off")
SLIDE_MODE_LABELS = {
    "auto": "Auto (catcher decides)",
    "force_on": "Force slide step",
    "force_off": "Stay in standard delivery",
}


def _cycle_slide_mode(current: str) -> str:
    if current not in SLIDE_STEP_MODES:
        return SLIDE_STEP_MODES[0]
    idx = SLIDE_STEP_MODES.index(current)
    return SLIDE_STEP_MODES[(idx + 1) % len(SLIDE_STEP_MODES)]


def _display_slide_mode(mode: str) -> str:
    return SLIDE_MODE_LABELS.get(mode, SLIDE_MODE_LABELS["auto"])

def player_pitch_turn(pitcher, batter, state, *, io: Optional[IOInterface] = None):
    """
    Handles the User Interaction for a pitching turn.
    Returns: (PitchRepertoire Object, Location String)
    """
    if not hasattr(state, "user_slide_step_mode"):
        state.user_slide_step_mode = "auto"

    logger = io.log if io else print
    prompter = io.prompt if io else input

    logger(f"\n{Colour.HEADER}--- PITCHER INTERFACE ---{Colour.RESET}")
    logger(f"vs {batter.name} (Pow {batter.power} / Con {batter.contact})")
    logger(f"Count: {state.balls}-{state.strikes} | Outs: {state.outs}")
    hints = describe_batter_tells(state, batter)
    if hints:
        logger(f"Intel: {' | '.join(hints)}")
    slide_status = _display_slide_mode(getattr(state, "user_slide_step_mode", "auto"))
    logger(f"Strategy: {Colour.gold}{slide_status}{Colour.RESET}")
    
    # Check runners for pickoff context
    has_runners = any(r is not None for r in state.runners)

    # 1. Get Arsenal
    arsenal = get_arsenal(pitcher.id)
    
    # 2. Display Options
    logger(f"{Colour.CYAN}Select Pitch:{Colour.RESET}")
    for idx, pitch in enumerate(arsenal):
        logger(f" {idx+1}. {pitch.pitch_name} (Qual: {pitch.quality})")
    
    if has_runners:
        logger(f" {len(arsenal)+1}. PICKOFF ATTEMPT")
        logger(f" {len(arsenal)+2}. PITCH OUT")
        logger(f" {len(arsenal)+3}. TOGGLE SLIDE STEP")

    # 3. Input Loop for Pitch/Action
    selected_pitch = None
    special_action = None

    while not selected_pitch and not special_action:
        try:
            choice = prompter(f"Command (1-{len(arsenal) + (3 if has_runners else 0)}): ")
            idx = int(choice) - 1
            
            if 0 <= idx < len(arsenal):
                selected_pitch = arsenal[idx]
            elif has_runners and idx == len(arsenal):
                return None, "Pickoff" # Special return
            elif has_runners and idx == len(arsenal) + 1:
                return None, "PitchOut" # Special return
            elif has_runners and idx == len(arsenal) + 2:
                current = getattr(state, "user_slide_step_mode", "auto")
                state.user_slide_step_mode = _cycle_slide_mode(current)
                logger(f" >> Switched to: {_display_slide_mode(state.user_slide_step_mode)}")
                # Continue the selection loop with updated strategy.
                selected_pitch = None
                special_action = None
                continue
            else:
                logger("Invalid selection.")
        except ValueError:
            logger("Please enter a number.")

    # 4. Input Loop for Location (Only if pitching normally)
    logger(f"\n{Colour.CYAN}Select Location:{Colour.RESET}")
    logger(" 1. ZONE (Standard)")
    logger(" 2. CHASE (Edge/Ball - Harder to hit, might walk)")
    
    location = "Zone"
    valid_loc = False
    while not valid_loc:
        choice = prompter("Target (1-2): ")
        if choice == '1':
            location = "Zone"
            valid_loc = True
        elif choice == '2':
            location = "Chase"
            valid_loc = True
        else:
            logger("Invalid target.")

    logger(f" > Throwing {selected_pitch.pitch_name} to {location}...")
    return selected_pitch, location


def prompt_runner_threat_controls(pitcher, state, *, io: Optional[IOInterface] = None) -> None:
    """Allow human pitchers to react to steals/pickoffs before the pitch."""
    logger = io.log if io else print
    prompter = io.prompt if io else input
    runners = list(getattr(state, "runners", []) or [])
    runner_first = runners[0] if len(runners) > 0 else None
    runner_second = runners[1] if len(runners) > 1 else None
    if not runner_first and not runner_second:
        return

    slide_mode = getattr(state, "user_slide_step_mode", "auto")
    logger(f"\n{Colour.CYAN}[Runner Pressure]{Colour.RESET} Slide Step: {_display_slide_mode(slide_mode)}")
    if runner_first:
        logger(f"   - Runner on first: {getattr(runner_first, 'name', getattr(runner_first, 'last_name', 'Runner'))}")
    if runner_second:
        logger(f"   - Runner on second: {getattr(runner_second, 'name', getattr(runner_second, 'last_name', 'Runner'))}")

    while True:
        prompt = prompter("   Actions? [Enter=continue / P=Throw over / S=Toggle slide step]: ").strip().lower()
        if not prompt:
            return
        if prompt in {"p", "1"}:
            if not runner_first:
                logger("   >> No runner at first to throw behind.")
                continue
            state._manual_pickoff_request = {"base": 0}
            pitcher_name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'Pitcher'))
            runner_name = getattr(runner_first, 'last_name', getattr(runner_first, 'name', 'Runner'))
            logger(f"   >> {pitcher_name} steps off and plans a snap throw to keep {runner_name} honest.")
            return
        if prompt in {"s", "2"}:
            slide_mode = _cycle_slide_mode(slide_mode)
            state.user_slide_step_mode = slide_mode
            logger(f"   >> Slide Step mode -> {_display_slide_mode(slide_mode)}")
            continue
        logger("   >> Invalid choice. Press Enter to continue the at-bat.")