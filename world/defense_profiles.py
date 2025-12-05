"""Team-level defensive personality profiles.

Phase 4 introduces lightweight defense profiles so that schools feel distinct in
the field.  The profiles provide coarse multipliers that the fielding engine
can use to scale range, arm utility, and reliability/error pressure.  The
values are intentionally simple so they can be overridden later via data files
or roster metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

__all__ = [
    "DefenseProfile",
    "DEFAULT_PROFILE",
    "DEFENSE_PROFILES",
    "get_defense_profile",
]


@dataclass(frozen=True)
class DefenseProfile:
    """Descriptor that tweaks how an entire defense behaves."""

    name: str
    range_multiplier: float = 1.0
    reliability_bonus: float = 0.0
    arm_bonus: float = 0.0
    error_rate: float = 1.0


DEFAULT_PROFILE = DefenseProfile("Neutral Defense")

DEFENSE_PROFILES: Dict[str, DefenseProfile] = {
    # School A prides itself on positioning and awareness.  Give them a
    # moderate range boost and steadier hands so routine plays stay routine.
    "school a": DefenseProfile(
        name="School A",
        range_multiplier=1.08,
        reliability_bonus=6.0,
        arm_bonus=2.5,
        error_rate=0.85,
    ),
    # School B wins slugfests but leaks runs on defense.  Reduce range and
    # reliability so more balls find grass and throws sail.
    "school b": DefenseProfile(
        name="School B",
        range_multiplier=0.93,
        reliability_bonus=-7.0,
        arm_bonus=-3.5,
        error_rate=1.2,
    ),
}


def get_defense_profile(team) -> DefenseProfile:
    """Return the profile associated with the team (fallbacks to default)."""

    if team is None:
        return DEFAULT_PROFILE
    key = getattr(team, "defense_profile", None)
    if not key:
        key = getattr(team, "name", "") or ""
    key = key.strip().lower()
    return DEFENSE_PROFILES.get(key, DEFAULT_PROFILE)
