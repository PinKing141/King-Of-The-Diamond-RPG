from typing import Optional

from core.io_interface import IOInterface
from ui.ui_display import Colour


SHIFT_LABELS = {
    "normal": "Standard Alignment",
    "double_play": "Double Play Depth",
    "infield_in": "Infield In (Stop Bunt)",
    "deep_outfield": "Deep Outfield (No Doubles)",
}

__all__ = ["prompt_defensive_shift", "prompt_hero_dive", "SHIFT_LABELS"]


def prompt_defensive_shift(current_shift: str | None, *, io: Optional[IOInterface] = None) -> str:
    """Prompt the user to select a defensive tactic before the pitch."""
    current_shift = current_shift or "normal"
    logger = io.log if io else print
    prompter = io.prompt if io else input

    logger(f"\n{Colour.CYAN}-- Defensive Tactics --{Colour.RESET}")
    logger(f" Current: {SHIFT_LABELS.get(current_shift, 'Standard Alignment')}")
    logger(" Enter to hold, or choose:")
    logger(" 1. Double Play Depth")
    logger(" 2. Infield In (Stop Bunt)")
    logger(" 3. Deep Outfield (No Doubles)")
    while True:
        raw = prompter("Set Alignment: ")
        if raw is None:
            return current_shift
        user_input = raw.strip()
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
        logger(" Invalid option. Press Enter to keep or select 1-3.")


def prompt_hero_dive(probability: float, defender_label: str, *, io: Optional[IOInterface] = None) -> str:
    pct = max(0.0, min(1.0, probability)) * 100
    logger = io.log if io else print
    prompter = io.prompt if io else input
    logger(f"\n{Colour.MAGENTA}Hero Dive Opportunity!{Colour.RESET}")
    logger(f" Target: {defender_label} | Catch Chance: {pct:.0f}%")
    logger(" 1. Play Safe (hold to a single)")
    logger(" 2. Dive! (Highlight catch or disaster)")
    while True:
        raw = prompter("Decision: ")
        if raw is None:
            return "safe"
        choice = raw.strip()
        if choice == "1":
            return "safe"
        if choice == "2":
            return "dive"
        logger(" Choose 1 or 2.")
