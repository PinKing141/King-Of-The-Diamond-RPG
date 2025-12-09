"""Shared helpers for lightweight world simulations."""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from core.rng import get_rng
from world_sim.services.sim_data import get_strength_map
from world_sim.services.sim_logging import log_event
from world_sim.strength_cache import StrengthCache, strength_cache

rng = get_rng()
MIN_WIN_PROB = 0.05
MAX_WIN_PROB = 0.95


def clear_strength_cache(cache: Optional[StrengthCache] = None) -> None:
    """Reset cached team strengths (use after roster/stat mutations)."""

    active = cache or strength_cache
    active.clear()
    log_event("strength_cache_cleared")


def reset_strength_cache(cache: Optional[StrengthCache] = None) -> None:
    """Alias for clearing cached strengths (season/sim lifecycle hook)."""

    active = cache or strength_cache
    active.reset()
    log_event("strength_cache_reset")


def calculate_team_strength(
    session,
    school_id: Optional[int],
    *,
    sample_size: int = 9,
    strength_map: Optional[Dict[int, int]] = None,
    cache: Optional[StrengthCache] = None,
) -> int:
    """Approximate team quality by averaging the top `sample_size` overall ratings with memoization."""

    active_cache = cache or strength_cache
    return active_cache.get(
        session,
        school_id,
        sample_size=sample_size,
        strength_map=strength_map,
    )


def quick_resolve_match(
    session,
    home_school,
    away_school,
    *,
    strength_map: Optional[Dict[int, int]] = None,
    cache: Optional[StrengthCache] = None,
) -> Tuple[object, str, bool, Optional[int], Optional[int]]:
    """Resolve an NPC match instantly while still allowing occasional upsets; returns winner/score/upset plus IDs."""

    ids = {getattr(home_school, "id", None), getattr(away_school, "id", None)}
    ids.discard(None)

    # If no map provided, pull strengths for the two teams in a single query; otherwise reuse caller cache.
    active_cache = cache or strength_cache
    local_map = strength_map if strength_map is not None else (get_strength_map(session, school_ids=ids, cache=active_cache) if ids else {})
    if strength_map is not None and local_map:
        active_cache.update_from_map({k: v for k, v in local_map.items() if v is not None})

    home_strength = calculate_team_strength(
        session,
        getattr(home_school, "id", None),
        strength_map=local_map,
        cache=active_cache,
    )
    away_strength = calculate_team_strength(
        session,
        getattr(away_school, "id", None),
        strength_map=local_map,
        cache=active_cache,
    )
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
    winner_id = getattr(winner, "id", None)
    loser_obj = away_school if winner is home_school else home_school
    loser_id = getattr(loser_obj, "id", None)
    score_str = f"{away_score} - {home_score}"
    return winner, score_str, is_upset, winner_id, loser_id
