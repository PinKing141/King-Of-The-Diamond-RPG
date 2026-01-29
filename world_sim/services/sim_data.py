"""Shared data helpers for sims (strengths/rosters/schools) with cache support."""
from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Dict, Iterable, List, Optional

from database.setup_db import School
from world_sim.data_access import load_strength_map, load_rosters
from world_sim.regions import get_region_for_prefecture
from world_sim.strength_cache import StrengthCache, strength_cache
from world_sim.services.sim_logging import log_event


def get_strength_map(
    session,
    *,
    school_ids: Optional[Iterable[int]] = None,
    sample_size: int = 9,
    cache: Optional[StrengthCache] = None,
) -> Dict[int, int]:
    """Fetch strengths and sync the shared strength cache (or provided cache)."""

    active_cache = cache or strength_cache
    strength_map = load_strength_map(session, school_ids=school_ids, sample_size=sample_size)
    active_cache.update_from_map(strength_map)
    return strength_map


def refresh_strength_map(
    session,
    school_ids: Iterable[int],
    *,
    sample_size: int = 9,
    cache: Optional[StrengthCache] = None,
) -> Dict[int, int]:
    """Refresh strengths for a set of schools, syncing cache."""

    return get_strength_map(session, school_ids=school_ids, sample_size=sample_size, cache=cache)


def get_rosters(session, school_ids: Iterable[int]):
    """Load rosters for schools (streamed). Returns live ORM objects; avoid unintended mutation."""

    roster_map = load_rosters(session, school_ids)
    log_event(
        "roster_load",
        school_count=len(roster_map),
        player_count=sum(len(players or []) for players in roster_map.values()),
    )
    return roster_map


def get_roster(session, school_id: int):
    """Convenience wrapper for a single roster."""

    return get_rosters(session, [school_id]).get(school_id, [])


def iter_schools_basic(session) -> Iterable[SimpleNamespace]:
    """Yield lightweight school records for regional/qualifier sims."""

    query = session.query(School.id, School.name, School.prefecture, School.prestige, School.city_name)
    try:
        rows = query.order_by(School.id).yield_per(256)
    except AttributeError:
        # Allow lightweight fake sessions used in tests that only support yield_per.
        rows = getattr(query, "yield_per", lambda _n: query)(256)
    for row in rows:
        if isinstance(row, (tuple, list)) and len(row) == 5:
            sid, name, prefecture, prestige, city_name = row
        else:
            sid = getattr(row, "id", None)
            name = getattr(row, "name", None)
            prefecture = getattr(row, "prefecture", None)
            prestige = getattr(row, "prestige", None)
            city_name = getattr(row, "city_name", None)
        yield SimpleNamespace(
            id=sid,
            name=name,
            prefecture=prefecture,
            prestige=prestige,
            city_name=city_name,
        )


def normalize_prefecture(prefecture: str, *, city_name: Optional[str] = None, school_id: Optional[int] = None) -> str:
    """Split Hokkaido into North/South (and allow future splits) for seeding/regions."""
    pref = (prefecture or "").strip()
    if pref.lower() != "hokkaido":
        return pref or ""
    north_cities = {
        "asahikawa",
        "wakkanai",
        "abashiri",
        "kitami",
        "kushiro",
        "obihiro",
        "nemuro",
        "monbetsu",
        "nayoro",
    }
    south_cities = {
        "sapporo",
        "otaru",
        "hakodate",
        "muroran",
        "tomakomai",
        "chitose",
        "iwamizawa",
        "ishikari",
    }
    city_key = (city_name or "").lower()
    if city_key in north_cities:
        return "Hokkaido North"
    if city_key in south_cities:
        return "Hokkaido South"
    # Deterministic fallback split by school_id parity to avoid oscillation.
    if school_id and school_id % 2 == 0:
        return "Hokkaido North"
    return "Hokkaido South"


def schools_by_region(session) -> Dict[str, List[SimpleNamespace]]:
    """Bucket schools by region using prefecture mapping, skipping Unknown."""

    buckets: Dict[str, List[SimpleNamespace]] = defaultdict(list)
    for school in iter_schools_basic(session):
        pref = normalize_prefecture(getattr(school, "prefecture", "") or "", city_name=getattr(school, "city_name", None), school_id=getattr(school, "id", None))
        school.prefecture = pref
        region = get_region_for_prefecture(pref)
        if region == "Unknown":
            continue
        buckets[region].append(school)
    return buckets
