import sys
from ui.ui_display import Colour
from match_engine.pitch_logic import get_arsenal, PitchResult, describe_batter_tells

# Flag to bypass blocking CLI prompts when a GUI layer supplies choices.
GUI_MODE = False


def enable_gui_mode(enabled: bool = True) -> None:
    """Flip pitcher UI into GUI (non-blocking) mode."""
    global GUI_MODE
    GUI_MODE = bool(enabled)

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

def player_pitch_turn(pitcher, batter, state):
    """
    Handles the User Interaction for a pitching turn.
    Returns: (PitchRepertoire Object, Location String)
    """
    if getattr(state, "gui_mode", False) or GUI_MODE:
        arsenal = get_arsenal(pitcher.id)
        fallback_pitch = arsenal[0] if arsenal else None
        return fallback_pitch, "Zone"

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


def prompt_runner_threat_controls(pitcher, state) -> None:
    """Allow human pitchers to react to steals/pickoffs before the pitch."""
    if getattr(state, "gui_mode", False) or GUI_MODE:
        return

    runners = list(getattr(state, "runners", []) or [])
    runner_first = runners[0] if len(runners) > 0 else None
    runner_second = runners[1] if len(runners) > 1 else None
    if not runner_first and not runner_second:
        return

    slide_mode = getattr(state, "user_slide_step_mode", "auto")
    print(f"\n{Colour.CYAN}[Runner Pressure]{Colour.RESET} Slide Step: {_display_slide_mode(slide_mode)}")
    if runner_first:
        print(f"   - Runner on first: {getattr(runner_first, 'name', getattr(runner_first, 'last_name', 'Runner'))}")
    if runner_second:
        print(f"   - Runner on second: {getattr(runner_second, 'name', getattr(runner_second, 'last_name', 'Runner'))}")

    while True:
        prompt = input("   Actions? [Enter=continue / P=Throw over / S=Toggle slide step]: ").strip().lower()
        if not prompt:
            return
        if prompt in {"p", "1"}:
            if not runner_first:
                print("   >> No runner at first to throw behind.")
                continue
            state._manual_pickoff_request = {"base": 0}
            pitcher_name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'Pitcher'))
            runner_name = getattr(runner_first, 'last_name', getattr(runner_first, 'name', 'Runner'))
            print(f"   >> {pitcher_name} steps off and plans a snap throw to keep {runner_name} honest.")
            return
        if prompt in {"s", "2"}:
            slide_mode = _cycle_slide_mode(slide_mode)
            state.user_slide_step_mode = slide_mode
            print(f"   >> Slide Step mode -> {_display_slide_mode(slide_mode)}")
            continue
        print("   >> Invalid choice. Press Enter to continue the at-bat.")