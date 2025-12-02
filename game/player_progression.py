"""Milestone-based progression helpers."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from database.setup_db import Game, GameState, Player, PlayerGameStats, PlayerMilestone
from game.rng import DeterministicRNG, get_rng
from game.skill_system import (
    SKILL_DEFINITIONS,
    grant_skill_by_key,
    player_has_skill,
)
from game.trait_logic import get_progression_speed_multiplier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MILESTONE_DATA_PATH = PROJECT_ROOT / "data" / "milestones.json"

logger = logging.getLogger(__name__)
PROGRESSION_DEBUG = os.getenv("PROGRESSION_DEBUG", "").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class MilestoneDefinition:
    key: str
    label: str
    skill_key: str
    description: str
    chance: float
    min_games: int
    condition: Callable[[Player, Dict[str, float]], bool]
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MilestoneUnlockResult:
    milestone_key: str
    milestone_label: str
    skill_key: str
    skill_name: str
    description: str


_milestone_rng = get_rng()
_MILESTONE_CACHE: Optional[List[MilestoneDefinition]] = None


def process_milestone_unlocks(
    session: Session,
    player: Player,
    *,
    season_year: Optional[int] = None,
    rng: Optional[DeterministicRNG] = None,
    milestone_definitions: Optional[Sequence[MilestoneDefinition]] = None,
    stats_cache: Optional[Dict[Tuple[int, Optional[int]], Dict[str, float]]] = None,
    owned_skill_keys: Optional[Set[str]] = None,
) -> List[MilestoneUnlockResult]:
    """Check milestone definitions and grant matching skills."""
    if not player or not player.id:
        return []

    if season_year is None:
        season_year = _current_season_year(session)

    stats = _collect_season_totals(
        session,
        player.id,
        season_year,
        stats_cache=stats_cache,
    )
    if stats["games_played"] == 0:
        return []

    if PROGRESSION_DEBUG:
        logger.debug(
            "Player %s milestone stats for season %s -> %s",
            player.id,
            season_year,
            stats,
        )

    random_source = rng or _milestone_rng
    results: List[MilestoneUnlockResult] = []

    definitions = list(milestone_definitions or get_milestone_definitions())
    owned_lookup = owned_skill_keys

    for milestone in definitions:
        if stats["games_played"] < milestone.min_games:
            if PROGRESSION_DEBUG:
                logger.debug(
                    "Player %s short of min games (%s/%s) for milestone %s",
                    player.id,
                    stats["games_played"],
                    milestone.min_games,
                    milestone.key,
                )
            continue
        if milestone.skill_key not in SKILL_DEFINITIONS:
            continue
        skill_key_lower = milestone.skill_key.lower()
        if owned_lookup is not None:
            if skill_key_lower in owned_lookup:
                if PROGRESSION_DEBUG:
                    logger.debug(
                        "Player %s already cached with milestone skill %s",
                        player.id,
                        milestone.skill_key,
                    )
                continue
        elif player_has_skill(player, milestone.skill_key):
            if PROGRESSION_DEBUG:
                logger.debug(
                    "Player %s already has milestone skill %s",
                    player.id,
                    milestone.skill_key,
                )
            continue
        if not milestone.condition(player, stats):
            if PROGRESSION_DEBUG:
                logger.debug(
                    "Player %s failed condition for milestone %s",
                    player.id,
                    milestone.key,
                )
            continue
        adjusted_chance = _clamp_chance(milestone.chance * _milestone_multiplier(player))
        roll = random_source.random()
        if roll > adjusted_chance:
            if PROGRESSION_DEBUG:
                logger.info(
                    "Player %s met milestone %s but roll %.3f exceeded chance %.2f",
                    player.id,
                    milestone.key,
                    roll,
                    adjusted_chance,
                )
            continue
        if PROGRESSION_DEBUG:
            logger.info(
                "Player %s passed milestone %s roll %.3f/%.2f",
                player.id,
                milestone.key,
                roll,
                adjusted_chance,
            )

        skill_name = grant_skill_by_key(
            session,
            player,
            milestone.skill_key,
            owned_cache=owned_skill_keys,
        )
        if not skill_name:
            if PROGRESSION_DEBUG:
                logger.debug(
                    "Player %s could not be granted milestone skill %s (duplicate?)",
                    player.id,
                    milestone.skill_key,
                )
            continue
        _record_player_milestone(session, player.id, milestone, season_year)
        results.append(
            MilestoneUnlockResult(
                milestone_key=milestone.key,
                milestone_label=milestone.label,
                skill_key=milestone.skill_key,
                skill_name=skill_name,
                description=milestone.description,
            )
        )

    if PROGRESSION_DEBUG and results:
        logger.info(
            "Player %s unlocked milestones: %s",
            player.id,
            [entry.milestone_key for entry in results],
        )

    return results


def _current_season_year(session: Session) -> Optional[int]:
    state = session.query(GameState).first()
    return getattr(state, "current_year", None) if state else None


def _collect_season_totals(
    session: Session,
    player_id: int,
    season_year: Optional[int],
    *,
    stats_cache: Optional[Dict[Tuple[int, Optional[int]], Dict[str, float]]] = None,
) -> Dict[str, float]:
    cache = stats_cache
    if cache is None:
        cache = getattr(session, "info", None)
        if cache is not None:
            cache = cache.setdefault("_milestone_stats", {})
    key = (player_id, season_year)
    if cache is not None and key in cache:
        return dict(cache[key])

    stats = _query_season_totals(session, player_id, season_year)
    if cache is not None:
        cache[key] = dict(stats)
    return stats


def _query_season_totals(session: Session, player_id: int, season_year: Optional[int]) -> Dict[str, float]:
    query = (
        session.query(
            func.count(PlayerGameStats.game_id).label("games_played"),
            func.coalesce(func.sum(PlayerGameStats.homeruns), 0).label("season_homeruns"),
            func.coalesce(func.sum(PlayerGameStats.rbi), 0).label("season_rbi"),
            func.coalesce(func.sum(PlayerGameStats.hits_batted), 0).label("season_hits"),
            func.coalesce(func.sum(PlayerGameStats.at_bats), 0).label("season_at_bats"),
            func.coalesce(
                func.sum(case((PlayerGameStats.rbi >= 3, 1), else_=0)),
                0,
            ).label("multi_rbi_games"),
            func.coalesce(func.max(PlayerGameStats.homeruns), 0).label("single_game_hr_max"),
            func.coalesce(func.max(PlayerGameStats.rbi), 0).label("single_game_rbi_max"),
            func.coalesce(func.max(PlayerGameStats.strikeouts_pitched), 0).label("single_game_k_max"),
            func.coalesce(func.sum(PlayerGameStats.strikeouts_pitched), 0).label("strikeouts_pitched"),
            func.coalesce(func.sum(PlayerGameStats.innings_pitched), 0.0).label("innings_pitched"),
            func.coalesce(func.sum(PlayerGameStats.fielding_errors), 0).label("fielding_errors"),
            func.coalesce(func.sum(PlayerGameStats.runs_allowed), 0).label("season_runs_allowed"),
        )
        .join(Game, Game.id == PlayerGameStats.game_id)
        .filter(PlayerGameStats.player_id == player_id)
    )
    if season_year is not None:
        query = query.filter(Game.season_year == season_year)

    row = query.one()

    stats = {
        "games_played": int(row.games_played or 0),
        "season_homeruns": int(row.season_homeruns or 0),
        "season_rbi": int(row.season_rbi or 0),
        "season_hits": int(row.season_hits or 0),
        "season_at_bats": int(row.season_at_bats or 0),
        "multi_rbi_games": int(row.multi_rbi_games or 0),
        "single_game_hr_max": int(row.single_game_hr_max or 0),
        "single_game_rbi_max": int(row.single_game_rbi_max or 0),
        "single_game_k_max": int(row.single_game_k_max or 0),
        "strikeouts_pitched": int(row.strikeouts_pitched or 0),
        "innings_pitched": float(row.innings_pitched or 0.0),
        "fielding_errors": int(row.fielding_errors or 0),
        "season_runs_allowed": int(row.season_runs_allowed or 0),
        "season_year": season_year,
    }
    innings = stats["innings_pitched"]
    stats["k_per_nine"] = ((stats["strikeouts_pitched"] * 9.0) / innings) if innings > 0 else 0.0
    at_bats = stats["season_at_bats"]
    stats["batting_average"] = ((stats["season_hits"]) / at_bats) if at_bats > 0 else 0.0
    return stats


def _is_pitcher(player: Player) -> bool:
    return (getattr(player, "position", "") or "").lower() == "pitcher"


def _milestone_multiplier(player: Player) -> float:
    base = get_progression_speed_multiplier(player)
    tag = (getattr(player, "growth_tag", "Normal") or "Normal").strip().lower()
    grade = (getattr(player, "potential_grade", "C") or "C").strip().upper()
    if tag == "limitless":
        base += 0.1
    elif tag == "sleeping giant":
        base += 0.05
    if grade == "S":
        base += 0.08
    elif grade == "A":
        base += 0.03

    owned = len(getattr(player, "skills", []) or [])
    penalty = 0.02 * max(0, owned - 3)
    return max(0.65, min(1.95, base - penalty))


def _clamp_chance(chance: float) -> float:
    return max(0.05, min(0.95, chance))


def _slugfest_condition(player: Player, stats: Dict[str, float], params: Dict[str, object]) -> bool:
    if _is_pitcher(player):
        return False
    return stats["single_game_hr_max"] >= 3 or (
        stats["season_homeruns"] >= 8 and stats["multi_rbi_games"] >= 3
    )


def _rbi_machine_condition(player: Player, stats: Dict[str, float], params: Dict[str, object]) -> bool:
    if _is_pitcher(player):
        return False
    return stats["multi_rbi_games"] >= 4 or stats["single_game_rbi_max"] >= 6


def _strikeout_showcase_condition(player: Player, stats: Dict[str, float], params: Dict[str, object]) -> bool:
    if not _is_pitcher(player):
        return False
    if stats["single_game_k_max"] >= 12:
        return True
    return stats["strikeouts_pitched"] >= 60 and stats["k_per_nine"] >= 10.0


def _flawless_glove_condition(player: Player, stats: Dict[str, float], params: Dict[str, object]) -> bool:
    if stats["games_played"] < 10:
        return False
    return stats["fielding_errors"] == 0

def _gap_machine_condition(player: Player, stats: Dict[str, float], params: Dict[str, object]) -> bool:
    if _is_pitcher(player):
        return False
    hits = stats["season_hits"]
    avg = stats["batting_average"]
    return hits >= int(params.get("min_hits", 22)) and avg >= float(params.get("min_avg", 0.33))


def _walkoff_proxy_condition(player: Player, stats: Dict[str, float], params: Dict[str, object]) -> bool:
    if _is_pitcher(player):
        return False
    return (
        stats["single_game_rbi_max"] >= int(params.get("single_game_rbi", 5))
        and stats["season_rbi"] >= int(params.get("season_rbi", 18))
    )


def _workhorse_condition(player: Player, stats: Dict[str, float], params: Dict[str, object]) -> bool:
    if not _is_pitcher(player):
        return False
    innings = stats["innings_pitched"]
    games = stats["games_played"]
    if innings < float(params.get("min_innings", 40.0)):
        return False
    if games == 0:
        return False
    avg_ip = innings / games
    return avg_ip >= float(params.get("min_avg_ip", 5.0))


def _shutdown_condition(player: Player, stats: Dict[str, float], params: Dict[str, object]) -> bool:
    if not _is_pitcher(player):
        return False
    runs_allowed = stats["season_runs_allowed"]
    innings = stats["innings_pitched"]
    k_per_nine = stats["k_per_nine"]
    if innings <= 0:
        return False
    era = (runs_allowed * 9.0) / innings
    return era <= float(params.get("max_era", 2.75)) and k_per_nine >= float(params.get("min_k_per_nine", 9.5))


CONDITION_REGISTRY: Dict[str, Callable[[Player, Dict[str, float], Dict[str, object]], bool]] = {
    "slugfest": _slugfest_condition,
    "rbi_machine": _rbi_machine_condition,
    "strikeout_showcase": _strikeout_showcase_condition,
    "flawless_glove": _flawless_glove_condition,
    "gap_machine": _gap_machine_condition,
    "walkoff_proxy": _walkoff_proxy_condition,
    "workhorse": _workhorse_condition,
    "shutdown": _shutdown_condition,
}


def _default_milestone_payload() -> List[Dict[str, object]]:
    return [
        {
            "key": "slugfest_hat_trick",
            "label": "Slugfest Hat Trick",
            "skill_key": "power_surge",
            "description": "Three-homer showcase or a barrage of long balls in a season.",
            "chance": 0.55,
            "min_games": 6,
            "condition_type": "slugfest",
        },
        {
            "key": "rbi_machine",
            "label": "RBI Machine",
            "skill_key": "clutch_hitter",
            "description": "Repeated multi-RBI games highlight late-inning heroics.",
            "chance": 0.45,
            "min_games": 8,
            "condition_type": "rbi_machine",
        },
        {
            "key": "strikeout_showcase",
            "label": "Strikeout Showcase",
            "skill_key": "strikeout_artist",
            "description": "Dominant strikeout outings unlock elite pitching aura.",
            "chance": 0.5,
            "min_games": 4,
            "condition_type": "strikeout_showcase",
        },
        {
            "key": "flawless_glove",
            "label": "Flawless Glove",
            "skill_key": "defensive_anchor",
            "description": "Error-free campaign cements gold-glove reputation.",
            "chance": 0.4,
            "min_games": 10,
            "condition_type": "flawless_glove",
        },
        {
            "key": "gap_artist",
            "label": "Gap-to-Gap Artist",
            "skill_key": "gap_specialist",
            "description": "Consistent multi-hit weeks turn a doubles threat into a legend.",
            "chance": 0.4,
            "min_games": 10,
            "condition_type": "gap_machine",
            "params": {"min_hits": 24, "min_avg": 0.34},
        },
        {
            "key": "walkoff_spark",
            "label": "Walk-off Spark",
            "skill_key": "spark_plug",
            "description": "Massive RBI bursts ignite dugout celebrations.",
            "chance": 0.35,
            "min_games": 8,
            "condition_type": "walkoff_proxy",
            "params": {"single_game_rbi": 5, "season_rbi": 18},
        },
        {
            "key": "ironman_workhorse",
            "label": "Ironman Streak",
            "skill_key": "workhorse",
            "description": "Stacked innings totals prove this ace never leaves the hill.",
            "chance": 0.5,
            "min_games": 6,
            "condition_type": "workhorse",
            "params": {"min_innings": 45.0, "min_avg_ip": 5.5},
        },
        {
            "key": "shutdown_specialist",
            "label": "Shutdown Specialist",
            "skill_key": "situational_ace",
            "description": "Low-ERA dominance and strikeout punch fuel bullpen legend.",
            "chance": 0.45,
            "min_games": 5,
            "condition_type": "shutdown",
            "params": {"max_era": 2.75, "min_k_per_nine": 9.5},
        },
    ]


def _build_definition(entry: Dict[str, object]) -> Optional[MilestoneDefinition]:
    cond_type = entry.get("condition_type")
    factory = CONDITION_REGISTRY.get(str(cond_type))
    if not factory:
        return None
    params = entry.get("params", {}) or {}

    def _condition(player: Player, stats: Dict[str, float], *, _factory=factory, _params=params):
        return _factory(player, stats, _params)

    try:
        return MilestoneDefinition(
            key=str(entry["key"]),
            label=str(entry.get("label", entry["key"])),
            skill_key=str(entry["skill_key"]),
            description=str(entry.get("description", "")),
            chance=float(entry.get("chance", 0.3)),
            min_games=int(entry.get("min_games", 5)),
            condition=_condition,
            metadata={"condition_type": cond_type, "params": params},
        )
    except KeyError:
        return None


def _load_milestone_payload() -> List[Dict[str, object]]:
    try:
        with MILESTONE_DATA_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, list) and data:
                return data
    except FileNotFoundError:
        pass
    return _default_milestone_payload()


def get_milestone_definitions() -> List[MilestoneDefinition]:
    global _MILESTONE_CACHE
    if _MILESTONE_CACHE is None:
        payload = _load_milestone_payload()
        definitions: List[MilestoneDefinition] = []
        for entry in payload:
            definition = _build_definition(entry)
            if definition:
                definitions.append(definition)
        _MILESTONE_CACHE = definitions
    return _MILESTONE_CACHE


def reload_milestone_definitions() -> List[MilestoneDefinition]:
    global _MILESTONE_CACHE
    _MILESTONE_CACHE = None
    return get_milestone_definitions()


def get_milestone_by_key(key: str) -> Optional[MilestoneDefinition]:
    for milestone in get_milestone_definitions():
        if milestone.key == key:
            return milestone
    return None


def _record_player_milestone(
    session: Session,
    player_id: int,
    milestone: MilestoneDefinition,
    season_year: Optional[int],
) -> PlayerMilestone:
    if not player_id:
        raise ValueError("player_id required for milestone logging")
    year = season_year if season_year is not None else 0
    existing = (
        session.query(PlayerMilestone)
        .filter(
            PlayerMilestone.player_id == player_id,
            PlayerMilestone.milestone_key == milestone.key,
            PlayerMilestone.season_year == year,
        )
        .one_or_none()
    )
    if existing:
        return existing

    entry = PlayerMilestone(
        player_id=player_id,
        milestone_key=milestone.key,
        milestone_label=milestone.label,
        description=milestone.description,
        skill_key=milestone.skill_key,
        season_year=year,
    )
    session.add(entry)
    session.flush()
    return entry


def fetch_player_milestone_tags(
    session: Session, player_ids: Sequence[int]
) -> Dict[int, List[Dict[str, object]]]:
    if not player_ids:
        return {}
    valid_ids = [pid for pid in set(player_ids) if pid]
    if not valid_ids:
        return {}
    rows: Sequence[PlayerMilestone] = (
        session.query(PlayerMilestone)
        .filter(PlayerMilestone.player_id.in_(valid_ids))
        .all()
    )
    mapping: Dict[int, List[Dict[str, object]]] = {}
    for row in rows:
        entry = {
            "key": row.milestone_key,
            "label": row.milestone_label or row.milestone_key,
            "skill_key": row.skill_key,
            "season_year": row.season_year,
        }
        mapping.setdefault(row.player_id, []).append(entry)
    return mapping


__all__ = [
    "process_milestone_unlocks",
    "MilestoneUnlockResult",
    "get_milestone_definitions",
    "reload_milestone_definitions",
    "get_milestone_by_key",
    "fetch_player_milestone_tags",
]
