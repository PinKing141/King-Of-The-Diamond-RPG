"""Autumn regional (8-block) simulator feeding Spring Senbatsu invites.

NOTE: This module currently uses direct print() calls with UI color codes.
Future refactor should accept an IOInterface or logging callback to properly
separate presentation from simulation logic. See docs/MVC_ARCHITECTURE.md
"""
from __future__ import annotations

from collections import defaultdict
import logging
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.exc import SQLAlchemyError

from core.io_interface import IOInterface
from database.setup_db import School
from core.rng import get_rng
from world_sim.regions import REGION_MAP, get_region_for_prefecture
from world_sim.sim_utils import calculate_team_strength, quick_resolve_match, clear_strength_cache
from world_sim.strength_cache import StrengthCache, strength_cache_scope
from world_sim.services.sim_data import get_strength_map, refresh_strength_map, schools_by_region
from world_sim.services.sim_logging import log_event
from match_engine.resolver import resolve_match

rng = get_rng()
LOG = logging.getLogger(__name__)

# Regions with additional bid for the runner-up in most years.
RUNNER_UP_REGIONS = {"Kanto", "Kinki", "Kyushu"}


def run_autumn_regionals(
    session,
    user_school_id: int,
    context=None,
    *,
    allow_user_control: bool = True,
    verbose: bool = True,
    io: IOInterface | None = None,
    events: Optional[List[Dict[str, object]]] = None,
) -> List[int]:
    """
    Simulate the Autumn regional (Shuki Chiku) tournaments across the 8 blocks.

    Returns a list of school IDs that earn Spring Senbatsu consideration.
    """

    logger = io.log if io else (lambda *args, **kwargs: None)
    with strength_cache_scope() as cache:
        clear_strength_cache(cache)

        if verbose:
            logger(f"\n=== AUTUMN REGIONALS: ROAD TO SENBATSU ===")
        if events is not None:
            events.append({"type": "regionals_start"})
        spring_ticket_winners: List[int] = []

        region_buckets: Dict[str, List[School]] = {region: [] for region in REGION_MAP}
        strength_cache: Dict[int, int] = get_strength_map(session, cache=cache)
        region_buckets = schools_by_region(session)

        for region_name, schools_in_region in region_buckets.items():
            if not schools_in_region:
                continue

            entrants = _pick_prefecture_reps(session, schools_in_region, strength_cache, cache=cache)
            if len(entrants) < 2:
                continue

            champion, runner_up = _simulate_block(
                session,
                entrants,
                region_name,
                user_school_id,
                context=context,
                allow_user_control=allow_user_control,
                verbose=verbose,
                io=io,
                events=events,
                strength_cache=strength_cache,
                cache=cache,
            )
            if champion:
                spring_ticket_winners.append(getattr(champion, "id", None))
            if runner_up and region_name in RUNNER_UP_REGIONS:
                spring_ticket_winners.append(getattr(runner_up, "id", None))

            if verbose and champion:
                user_marker = " (YOU)" if getattr(champion, "id", None) == user_school_id else ""
                logger(f"   {region_name} Champion: {champion.name}{user_marker}")
            if verbose and runner_up and region_name in RUNNER_UP_REGIONS:
                logger(f"   {region_name} Runner-Up: {runner_up.name}")
            if events is not None:
                events.append(
                    {
                        "type": "region_result",
                        "region": region_name,
                        "champion": getattr(champion, "id", None),
                        "runner_up": getattr(runner_up, "id", None) if region_name in RUNNER_UP_REGIONS else None,
                    }
                )

        return [sid for sid in spring_ticket_winners if sid]


def _pick_prefecture_reps(
    session,
    schools: Sequence[School],
    strength_cache: Dict[int, int],
    *,
    cache: Optional[StrengthCache] = None,
) -> List[School]:
    """Select top two teams per prefecture by strength/prestige."""

    by_pref: Dict[str, List[Tuple[School, int]]] = defaultdict(list)
    for school in schools:
        pref = getattr(school, "prefecture", None) or ""
        sid = getattr(school, "id", None)
        strength = strength_cache.get(sid)
        if strength is None and sid is not None:
            strength = calculate_team_strength(session, sid, strength_map=strength_cache, cache=cache)
            strength_cache[sid] = strength
        prestige = getattr(school, "prestige", 0) or 0
        score = (strength * 0.7) + (prestige * 0.3)
        by_pref[pref].append((school, int(score)))

    entrants: List[School] = []
    for bucket in by_pref.values():
        bucket.sort(key=lambda row: row[1], reverse=True)
        entrants.extend([row[0] for row in bucket[:2]])

    rng.shuffle(entrants)
    return entrants


def _simulate_block(
    session,
    entrants: List[School],
    region_name: str,
    user_school_id: int,
    *,
    context=None,
    allow_user_control: bool = True,
    verbose: bool = True,
    io: IOInterface | None = None,
    events: Optional[List[Dict[str, object]]] = None,
    strength_cache: Dict[int, int] | None = None,
    cache: Optional[StrengthCache] = None,
) -> Tuple[Optional[School], Optional[School]]:
    """Run a single-elimination block; returns (champion, runner_up)."""

    bracket = list(entrants)
    rng.shuffle(bracket)
    runner_up: Optional[School] = None
    round_num = 1

    logger = io.log if io else (lambda *args, **kwargs: None)
    strengths = strength_cache or {}

    while len(bracket) > 1:
        if verbose:
            logger(f"\n{region_name} Block — Round {round_num} ({len(bracket)} teams)")
        next_round: List[School] = []
        # If odd, give a bye to the strongest remaining team to mirror seeding.
        if len(bracket) % 2 == 1:
            def _strength(school: School) -> int:
                sid = getattr(school, "id", None)
                val = strengths.get(sid)
                if val is None and sid is not None:
                    val = calculate_team_strength(session, sid, strength_map=strengths, cache=cache)
                    strengths[sid] = val
                return val or 0

            bracket.sort(key=_strength, reverse=True)
            bye_team = bracket.pop(0)
            next_round.append(bye_team)
            if verbose:
                logger(f"   Bye: {bye_team.name}")

        for idx in range(0, len(bracket), 2):
            home = bracket[idx]
            away = bracket[idx + 1]
            is_user = allow_user_control and user_school_id in {home.id, away.id}

            if is_user:
                rival_ctx = context.get_temp_effect("rival_match_context") if context else None
                rival_presentation = context.get_temp_effect("rival_presentation") if context else None
                logger(f"   YOU vs {away.name if home.id == user_school_id else home.name}")
                listeners = getattr(context, "match_event_listeners", None) if context else None
                try:
                    winner, score = resolve_match(
                        home,
                        away,
                        tournament_name=f"{region_name} Autumn",
                        mode="standard",
                        silent=False,
                        rival_match_context=rival_ctx,
                        rival_presentation=rival_presentation,
                        event_listeners=listeners,
                        session=session,
                    )
                except (SQLAlchemyError, RuntimeError, ValueError) as exc:
                    session.rollback()
                    LOG.exception(
                        "resolve_match failed for region=%s home=%s away=%s; falling back to quick result",
                        region_name,
                        getattr(home, "id", None),
                        getattr(away, "id", None),
                    )
                    logger(f"   Resolve failed; falling back to quick result ({exc})")
                    winner, score, *_ = quick_resolve_match(session, home, away, strength_map=strengths, cache=cache)
                    log_event(
                        "regional_quick_resolve_fallback",
                        region=region_name,
                        home_id=getattr(home, "id", None),
                        away_id=getattr(away, "id", None),
                        error=str(exc),
                    )
                loser = away if winner is home else home
                if verbose:
                    logger(f"   Result: {winner.name} wins ({score})")
            else:
                winner, score, upset, *_ids = quick_resolve_match(session, home, away, strength_map=strengths, cache=cache)
                loser = away if winner is home else home
                if verbose:
                    note = " (UPSET)" if upset else ""
                    logger(f"   {home.name} vs {away.name} -> {winner.name} {score}{note}")

            log_event(
                "regional_match_resolved",
                region=region_name,
                round=round_num,
                home_id=getattr(home, "id", None),
                away_id=getattr(away, "id", None),
                winner_id=getattr(winner, "id", None),
                score=score,
                upset=bool(locals().get("upset", False)),
            )

            if events is not None:
                events.append(
                    {
                        "type": "regional_match",
                        "region": region_name,
                        "round": round_num,
                        "home": getattr(home, "id", None),
                        "away": getattr(away, "id", None),
                        "winner": getattr(winner, "id", None),
                        "score": score,
                    }
                )
            next_round.append(winner)
            if len(bracket) == 2:
                runner_up = loser

        bracket = next_round
        strengths = refresh_strength_map(
            session,
            school_ids=[sid for s in bracket if (sid := getattr(s, "id", None)) is not None],
            cache=cache,
        ) or strengths
        round_num += 1

    champion = bracket[0] if bracket else None
    return champion, runner_up
