"""Tiny data-access helpers to centralize common lightweight queries.

Deprecated: prefer `world_sim.services.sim_data` as the public surface. This module
remains as the thin implementation shim consumed by sim_data/strength_cache.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from database.setup_db import Player


def load_strength_map(session, *, school_ids: Optional[Iterable[int]] = None, sample_size: int = 9) -> Dict[int, int]:
    """Return a map of school_id -> average overall of top `sample_size` players.

    This mirrors the strength heuristic used in quick NPC simulations but performs
    it in a single query to avoid per-school round-trips.
    """

    try:
        query = session.query(Player.school_id, Player.overall).filter(Player.school_id.isnot(None))
        if school_ids:
            query = query.filter(Player.school_id.in_(list(school_ids)))
        rows = query.order_by(Player.school_id, Player.overall.desc()).all()
    except AttributeError:
        # Support lightweight fake sessions used in tests.
        rows = []
    if not rows:
        return {}

    strength_map: Dict[int, int] = {}
    current_id: Optional[int] = None
    bucket: List[int] = []
    for school_id, overall in rows:
        if school_id != current_id:
            if bucket and current_id is not None:
                strength_map[current_id] = sum(bucket) // len(bucket)
            current_id = school_id
            bucket = []
        if len(bucket) < sample_size:
            bucket.append(overall or 0)
    if bucket and current_id is not None:
        strength_map[current_id] = sum(bucket) // len(bucket)
    return strength_map


def load_rosters(session, school_ids: Iterable[int]):
    """Return a map of school_id -> list of players ordered by overall desc.

    Note: returns live ORM objects; callers should avoid mutating players unless intending to persist.
    """

    ids = list(school_ids)
    if not ids:
        return {}
    roster_map = defaultdict(list)
    query = (
        session.query(Player)
        .filter(Player.school_id.in_(ids))
        .order_by(Player.school_id, Player.overall.desc())
    )
    for player in query.yield_per(256):
        roster_map[getattr(player, "school_id", None)].append(player)
    return roster_map
