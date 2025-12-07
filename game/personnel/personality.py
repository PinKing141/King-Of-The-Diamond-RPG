from __future__ import annotations

import random
from typing import Dict, Optional

from database.setup_db import School
from world.school_philosophy import PHILOSOPHY_MATRIX


def _clamp(val: float, low: int = 1, high: int = 100) -> int:
    return max(low, min(high, int(round(val))))


def _profile_for_school(school: Optional[School]) -> dict:
    if not school or not school.philosophy:
        return {}
    return PHILOSOPHY_MATRIX.get(school.philosophy, {})


def _numeric(attribute: str, profile: dict, school: Optional[School], default: float) -> float:
    if attribute in profile:
        return profile[attribute]
    if not school:
        return default
    return getattr(school, attribute, default) if getattr(school, attribute, None) is not None else default


def _roll_traits(school: Optional[School], *, coach: bool = False) -> Dict[str, int]:
    profile = _profile_for_school(school)
    prestige = _numeric('prestige', profile, school, 50)
    seniority = _numeric('seniority_bias', profile, school, 0.5)
    trust = _numeric('trust_weight', profile, school, 0.5)
    stats_weight = _numeric('stats_weight', profile, school, 0.5)
    injury_tol = _numeric('injury_tolerance', profile, school, 0.0)
    focus = (profile.get('focus') or getattr(school, 'focus', '') or '').lower()
    training_style = (profile.get('training_style') or getattr(school, 'training_style', '') or '').lower()

    drive_base = random.randint(42, 78) if coach else random.randint(30, 70)
    loyalty_base = random.randint(45, 80) if coach else random.randint(30, 70)
    volatility_base = random.randint(18, 55) if coach else random.randint(25, 65)

    drive_bias = (prestige - 50) * (0.6 if coach else 0.4)
    drive_bias += (stats_weight - 0.5) * 35
    if focus in {'ace', 'pitching', 'technical'}:
        drive_bias += 6
    elif focus in {'balanced', 'defense'}:
        drive_bias += 2
    elif focus in {'random', 'average'}:
        drive_bias -= 3

    loyalty_bias = (seniority - 0.5) * 45 + (trust - 0.5) * 40
    if training_style in {'traditional', 'spirit'}:
        loyalty_bias += 6
    if focus in {'balanced', 'defense', 'battery'}:
        loyalty_bias += 4
    if focus in {'gamblers', 'power'}:
        loyalty_bias -= 4

    volatility_bias = injury_tol * 28
    if focus in {'power', 'guts', 'gamblers', 'random'}:
        volatility_bias += 10
    if focus in {'balanced', 'technical', 'defense'}:
        volatility_bias -= 6
    if training_style == 'spirit':
        volatility_bias += 6
    elif training_style == 'modern':
        volatility_bias -= 4

    if coach:
        volatility_bias *= 0.7  # coaches temper volatility slightly

    jitter = 4 if coach else 7

    return {
        'drive': _clamp(drive_base + drive_bias + random.randint(-jitter, jitter)),
        'loyalty': _clamp(loyalty_base + loyalty_bias + random.randint(-jitter, jitter)),
        'volatility': _clamp(volatility_base + volatility_bias + random.randint(-jitter, jitter)),
    }


def roll_player_personality(school: Optional[School]) -> Dict[str, int]:
    """Return drive/loyalty/volatility ratings for a player recruit."""
    return _roll_traits(school, coach=False)


def roll_coach_personality(school: Optional[School]) -> Dict[str, int]:
    """Return drive/loyalty/volatility ratings tailored for coaches."""
    return _roll_traits(school, coach=True)
