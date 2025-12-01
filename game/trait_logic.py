"""Shared helpers for trait (skill) acquisition odds."""
from __future__ import annotations

import logging
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from database.setup_db import Player
from game.rng import DeterministicRNG, get_rng
from game.skill_system import grant_skill_by_key, list_meetable_skills

logger = logging.getLogger(__name__)

# Hidden growth tags and potential grades quietly push players forward (or hold them back).
_GROWTH_TAG_MULTIPLIERS = {
    "limitless": 1.45,
    "sleeping giant": 1.25,
    "supernova": 1.15,
    "grinder": 1.05,
    "normal": 1.0,
}
_POTENTIAL_GRADE_MULTIPLIERS = {
    "s": 1.35,
    "a": 1.2,
    "b": 1.05,
    "c": 0.9,
    "d": 0.85,
}

_INITIAL_TRAIT_CAP = 3
_trait_rng = get_rng()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_tag(tag: Optional[str]) -> str:
    return (tag or "Normal").strip().lower()


def _normalize_grade(grade: Optional[str]) -> str:
    return (grade or "C").strip().upper()


def get_progression_speed_multiplier(player: Player) -> float:
    """Return a quiet multiplier that speeds up or slows down overall growth."""
    tag = _normalize_tag(getattr(player, "growth_tag", "Normal"))
    grade = _normalize_grade(getattr(player, "potential_grade", "C"))
    tag_mult = _GROWTH_TAG_MULTIPLIERS.get(tag, 1.0)
    grade_mult = _POTENTIAL_GRADE_MULTIPLIERS.get(grade, 1.0)
    seniority_bonus = 1.0 + 0.05 * max(0, (getattr(player, "year", 1) or 1) - 1)
    return _clamp(tag_mult * grade_mult * seniority_bonus, 0.6, 1.85)


def ai_skill_unlock_probability(player: Player, skill_key: str, _: Optional[dict] = None) -> float:
    """Probability that an AI keeps a newly qualified skill during a roll."""
    progression = get_progression_speed_multiplier(player)
    base = 0.35 * progression

    # Early traits feel more achievable; stacked stars still rare.
    owned = len(getattr(player, "skills", []) or [])
    if owned == 0:
        base += 0.08
    base -= 0.025 * max(0, owned - 1)

    # Cinematic bursts for elite tools.
    if skill_key in {"clutch_hitter", "spark_plug", "power_surge"}:
        base += getattr(player, "clutch", 0) / 180.0
    elif skill_key in {"flame_thrower", "strikeout_artist", "control_freak"}:
        base += getattr(player, "velocity", 0) / 165.0
    elif skill_key in {"speed_demon", "gap_specialist"}:
        base += getattr(player, "speed", 0) / 190.0

    # Hidden potential tier nudges (limitless & S-tier always feel anime-worthy).
    grade = _normalize_grade(getattr(player, "potential_grade", "C"))
    if grade == "S":
        base += 0.08
    elif grade == "A":
        base += 0.04

    return _clamp(base, 0.15, 0.92)


def _initial_trait_weights(multiplier: float) -> Sequence[float]:
    """Return sampling weights for [0, 1, 2, 3] initial traits."""
    multiplier = _clamp(multiplier, 0.6, 1.85)
    zero = max(50.0, 90.0 / multiplier)
    one = 12.0 * multiplier
    two = 1.8 * max(1.0, multiplier - 0.05)
    three = 0.45 * max(1.0, multiplier - 0.2)
    return (zero, one, two, three)


def roll_initial_trait_slots(player: Player, rng: Optional[DeterministicRNG] = None) -> int:
    rng = rng or _trait_rng
    weights = _initial_trait_weights(get_progression_speed_multiplier(player))
    slots = rng.choices([0, 1, 2, 3], weights=weights, k=1)[0]
    return min(int(slots), _INITIAL_TRAIT_CAP)


def seed_initial_traits(
    session: Session,
    players: Iterable[Player],
    *,
    rng: Optional[DeterministicRNG] = None,
) -> int:
    """Grant a handful of birth traits to AI recruits based on hidden upside."""
    rng = rng or _trait_rng
    total = 0
    for player in players:
        slots = roll_initial_trait_slots(player, rng)
        if slots <= 0:
            continue
        eligible = list_meetable_skills(player)
        if not eligible:
            continue
        eligible = eligible.copy()
        rng.shuffle(eligible)
        granted = 0
        for key in eligible:
            if granted >= slots:
                break
            if grant_skill_by_key(session, player, key):
                granted += 1
        total += granted
    if total:
        session.flush()
        logger.debug("Seeded %s initial AI traits", total)
    return total


def grant_user_creation_trait_rolls(
    session: Session,
    player: Player,
    *,
    rolls: int = 3,
    rng: Optional[DeterministicRNG] = None,
) -> int:
    """Give the user a few blind rolls to start with a signature trait."""
    rng = rng or _trait_rng
    attempts = max(0, rolls)
    granted = 0
    for _ in range(attempts):
        eligible = list_meetable_skills(player)
        if not eligible:
            break
        chance = _clamp(0.28 * get_progression_speed_multiplier(player), 0.12, 0.85)
        roll = rng.random()
        if roll > chance:
            continue
        key = rng.choice(eligible)
        if grant_skill_by_key(session, player, key):
            granted += 1
            break
    if granted:
        logger.info("Hero %s earned %s starting trait(s)", player.id, granted)
    return granted


__all__ = [
    "ai_skill_unlock_probability",
    "get_progression_speed_multiplier",
    "grant_user_creation_trait_rolls",
    "roll_initial_trait_slots",
    "seed_initial_traits",
]
