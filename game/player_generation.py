"""Player generation helpers for trait assignment."""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from game.rng import DeterministicRNG, get_rng
from game.skill_system import (
    SKILL_DEFINITIONS,
    grant_skill_by_key,
    list_player_skill_keys,
)

_NEGATIVE_TRAITS = [
    key
    for key, data in SKILL_DEFINITIONS.items()
    if data.get("alignment") == "negative"
]


def maybe_assign_bad_trait(
    session: Session,
    player,
    *,
    chance: float = 0.1,
    rng: Optional[DeterministicRNG] = None,
) -> Optional[str]:
    """Give a newly generated player a negative trait with the provided odds."""
    if not player or not player.id or not _NEGATIVE_TRAITS:
        return None

    owned = set(list_player_skill_keys(player))
    if len(owned) >= 3:
        return None

    chance = max(0.0, min(1.0, chance))
    rng = rng or get_rng()
    if rng.random() > chance:
        return None

    pool = [key for key in _NEGATIVE_TRAITS if key not in owned]
    if not pool:
        return None

    chosen = rng.choice(pool)
    return grant_skill_by_key(session, player, chosen)


def seed_negative_traits(
    session: Session, players: Iterable, *, chance: float = 0.1, rng: Optional[DeterministicRNG] = None
) -> int:
    """Iterate through players, rolling for a negative trait assignment."""
    rng = rng or get_rng()
    total = 0
    for player in players:
        if maybe_assign_bad_trait(session, player, chance=chance, rng=rng):
            total += 1
    if total:
        session.flush()
    return total


__all__ = ["maybe_assign_bad_trait", "seed_negative_traits"]
