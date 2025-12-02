from ui.ui_display import Colour


SHIFT_LABELS = {
    "normal": "Standard Alignment",
    "double_play": "Double Play Depth",
    "infield_in": "Infield In (Stop Bunt)",
    "deep_outfield": "Deep Outfield (No Doubles)",
}

__all__ = ["prompt_defensive_shift", "prompt_hero_dive", "SHIFT_LABELS"]


def prompt_defensive_shift(current_shift: str | None) -> str:
    """Prompt the user to select a defensive tactic before the pitch."""
    current_shift = current_shift or "normal"
    print(f"\n{Colour.CYAN}-- Defensive Tactics --{Colour.RESET}")
    print(f" Current: {SHIFT_LABELS.get(current_shift, 'Standard Alignment')}")
    print(" Enter to hold, or choose:")
    print(" 1. Double Play Depth")
    print(" 2. Infield In (Stop Bunt)")
    print(" 3. Deep Outfield (No Doubles)")
    while True:
        user_input = input("Set Alignment: ").strip()
        if not user_input:
            return current_shift
        if user_input == "1":
            return "double_play"
        if user_input == "2":
            return "infield_in"
        if user_input == "3":
            return "deep_outfield"
        if user_input in {"0", "normal"}:
            return "normal"
        print(" Invalid option. Press Enter to keep or select 1-3.")


def prompt_hero_dive(probability: float, defender_label: str) -> str:
    pct = max(0.0, min(1.0, probability)) * 100
    print(f"\n{Colour.MAGENTA}Hero Dive Opportunity!{Colour.RESET}")
    print(f" Target: {defender_label} | Catch Chance: {pct:.0f}%")
    print(" 1. Play Safe (hold to a single)")
    print(" 2. Dive! (Highlight catch or disaster)")
    while True:
        choice = input("Decision: ").strip()
        if choice == "1":
            return "safe"
        if choice == "2":
            return "dive"
        print(" Choose 1 or 2.")
