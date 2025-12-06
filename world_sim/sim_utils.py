"""Shared helpers for lightweight world simulations."""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from database.setup_db import Player
from game.rng import get_rng

rng = get_rng()
MIN_WIN_PROB = 0.05
MAX_WIN_PROB = 0.95


_strength_cache: Dict[int, int] = {}


def _prime_strength_cache(session, *, sample_size: int = 9) -> None:
    """Eagerly build strength cache for all schools in one pass (avoids per-school queries)."""

    if _strength_cache:
        return
    rows = (
        session.query(Player.school_id, Player.overall)
        .filter(Player.school_id.isnot(None))
        .order_by(Player.school_id, Player.overall.desc())
        .all()
    )
    if not rows:
        return
    current_id = None
    bucket = []
    for school_id, overall in rows:
        if school_id != current_id:
            if bucket:
                _strength_cache[current_id] = sum(bucket) // len(bucket)
            current_id = school_id
            bucket = []
        if len(bucket) < sample_size:
            bucket.append(overall or 0)
    if bucket and current_id is not None:
        _strength_cache[current_id] = sum(bucket) // len(bucket)


def calculate_team_strength(session, school_id: Optional[int], *, sample_size: int = 9) -> int:
    """Approximate team quality by averaging the top `sample_size` overall ratings with memoization."""

    if not school_id:
        return 0
    if school_id in _strength_cache:
        return _strength_cache[school_id]

    # Build cache lazily in one query when first needed.
    _prime_strength_cache(session, sample_size=sample_size)
    if school_id in _strength_cache:
        return _strength_cache[school_id]

    players: Sequence[Player] = (
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

    _strength_cache[school_id] = strength
    return strength


def quick_resolve_match(session, home_school, away_school) -> Tuple[object, str, bool]:
    """Resolve an NPC match instantly while still allowing occasional upsets."""

    home_strength = calculate_team_strength(session, getattr(home_school, "id", None))
    away_strength = calculate_team_strength(session, getattr(away_school, "id", None))
    delta = home_strength - away_strength
    win_prob = 0.50 + (delta * 0.025)
    win_prob = max(MIN_WIN_PROB, min(MAX_WIN_PROB, win_prob))
    home_wins = rng.random() < win_prob
    dominance = abs(delta)
    is_upset = (home_wins and delta < -5) or ((not home_wins) and delta > 5)

    def _scoreline(favorite: bool) -> Tuple[int, int]:
        if is_upset:
            winner = rng.randint(2, 5)
            loser = max(0, winner - rng.randint(1, 2))
            return winner, loser
        if favorite and dominance > 15 and rng.random() < 0.4:
            return rng.randint(7, 12), rng.randint(0, 3)
        winner = rng.randint(3, 8)
        loser = max(0, winner - rng.randint(1, 4))
        return winner, loser

    favorite_is_home = delta >= 0
    winner_runs, loser_runs = _scoreline(favorite_is_home if home_wins else not favorite_is_home)
    if home_wins:
        home_score, away_score = winner_runs, loser_runs
        winner = home_school
    else:
        home_score, away_score = loser_runs, winner_runs
        winner = away_school
    score_str = f"{away_score} - {home_score}"
    return winner, score_str, is_upset
