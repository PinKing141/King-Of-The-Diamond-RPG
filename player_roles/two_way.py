"""Utility helpers for generating two-way player profiles."""
from __future__ import annotations

import random
from typing import Optional, Tuple

from game.rng import get_rng

INFIELD_POSITIONS = {"Infielder", "1B", "2B", "3B", "SS"}
OUTFIELD_POSITIONS = {"Outfielder", "LF", "CF", "RF"}

DEFAULT_SECONDARY = {
    "Pitcher": ("Outfielder", "Infielder", "Catcher"),
    "Catcher": ("Infielder", "Outfielder"),
    "Infielder": ("Pitcher", "Outfielder"),
    "Outfielder": ("Pitcher", "Infielder"),
}


def roll_two_way_profile(primary_position: str, rng: Optional[object] = None) -> Tuple[bool, Optional[str]]:
    """Return (is_two_way, secondary_position) for a given primary position."""
    random_source = rng or get_rng()
    chance = 0.02
    if primary_position == "Pitcher":
        chance += 0.03
    elif primary_position == "Catcher":
        chance += 0.01

    if random_source.random() >= chance:
        return False, None

    options = DEFAULT_SECONDARY.get(primary_position, ("Infielder",))
    secondary = random_source.choice(options)
    return True, secondary
*** End of File
