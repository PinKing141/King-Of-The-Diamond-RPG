"""Deterministic RNG wrapper used across the game layer."""
from __future__ import annotations

import random
from typing import MutableSequence, Optional, Sequence, TypeVar

_T = TypeVar("_T")


class DeterministicRNG:
    """Wrapper around :class:`random.Random` that exposes common helpers."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self._random = random.Random(seed)

    def seed(self, seed_value: Optional[int]) -> None:
        """Reseed the underlying generator (``None`` resets to system state)."""
        self._random.seed(seed_value)

    def random(self) -> float:
        return self._random.random()

    def randint(self, a: int, b: int) -> int:
        return self._random.randint(a, b)

    def uniform(self, a: float, b: float) -> float:
        return self._random.uniform(a, b)

    def choice(self, seq: Sequence[_T]) -> _T:
        if not seq:
            raise ValueError("Cannot choose from an empty sequence")
        return self._random.choice(seq)

    def sample(self, population: Sequence[_T], k: int) -> list[_T]:
        return self._random.sample(population, k)

    def shuffle(self, seq: MutableSequence[_T]) -> None:
        self._random.shuffle(seq)


_global_rng = DeterministicRNG()


def get_rng() -> DeterministicRNG:
    """Return the shared RNG instance used throughout the simulation."""
    return _global_rng


def seed_global_rng(seed_value: Optional[int]) -> None:
    """Convenience helper for callers that just need to reseed the singleton."""
    _global_rng.seed(seed_value)


__all__ = ["DeterministicRNG", "get_rng", "seed_global_rng"]
