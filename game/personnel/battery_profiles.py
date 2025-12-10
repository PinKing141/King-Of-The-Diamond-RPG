"""Lightweight battery chemistry adapter.

Delegates to the richer generator in :mod:`game.battery_profiles` but preserves
the original two-field return shape for callers that only expect (title, desc).
"""
from __future__ import annotations

from typing import Tuple

from game.battery_profiles import analyze_battery_chemistry as _new_analyzer


def analyze_battery_chemistry(pitcher, catcher, trust_score: int | float = 50) -> Tuple[str, str]:
    title, desc, _color = _new_analyzer(pitcher, catcher, trust_score, None)
    return title, desc


__all__ = ["analyze_battery_chemistry"]
