"""Scoped strength cache helper to avoid global staleness."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, Iterator, Optional

from database.setup_db import Player
from world_sim.data_access import load_strength_map


class StrengthCache:
    def __init__(self) -> None:
        self._cache: Dict[int, int] = {}

    def clear(self) -> None:
        self._cache.clear()

    def reset(self) -> None:
        self.clear()

    def update_from_map(self, strength_map: Optional[Dict[int, int]]) -> None:
        if not strength_map:
            return
        for sid, strength in strength_map.items():
            if sid is None:
                continue
            if strength is not None:
                self._cache[sid] = strength

    def prime(self, session, *, sample_size: int = 9) -> None:
        if self._cache:
            return
        self.update_from_map(load_strength_map(session, sample_size=sample_size))

    def get(
        self,
        session,
        school_id: Optional[int],
        *,
        sample_size: int = 9,
        strength_map: Optional[Dict[int, int]] = None,
    ) -> int:
        if not school_id:
            return 0

        if strength_map is not None:
            if school_id not in strength_map:
                fetched = load_strength_map(session, school_ids=[school_id])
                strength_map.update(fetched)
            if school_id in strength_map:
                strength = strength_map[school_id] or 0
                self._cache[school_id] = strength
                return strength

        if school_id in self._cache:
            return self._cache[school_id]

        self.prime(session, sample_size=sample_size)
        if school_id in self._cache:
            return self._cache[school_id]

        players = (
            session.query(Player)
            .filter(Player.school_id == school_id)
            .order_by(Player.overall.desc())
            .limit(sample_size)
            .all()
        )
        if not players:
            strength = 0
        else:
            total = sum(getattr(player, "overall", 0) or 0 for player in players)
            strength = total // len(players)

        self._cache[school_id] = strength
        return strength


@contextmanager
def strength_cache_scope(existing: Optional[StrengthCache] = None) -> Iterator[StrengthCache]:
    """Provide a throwaway cache that is cleared on exit.

    This keeps the global singleton untouched while allowing per-sim isolation.
    """

    cache = existing or StrengthCache()
    try:
        yield cache
    finally:
        cache.clear()


strength_cache = StrengthCache()
