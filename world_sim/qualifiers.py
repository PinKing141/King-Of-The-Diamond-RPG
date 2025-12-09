"""Tournament qualifier simulation for regional tournaments.

NOTE: This module currently uses direct print() calls with UI color codes.
Future refactor should accept an IOInterface or logging callback to properly
separate presentation from simulation logic. See docs/MVC_ARCHITECTURE.md
"""
import logging
import math
from typing import Dict, List, Optional

from core.io_interface import IOInterface
from core.rng import get_rng
from database.setup_db import School
from match_engine.resolver import resolve_match
from world_sim.services.sim_data import get_strength_map
from world_sim.services.sim_logging import log_event
from world_sim.sim_utils import clear_strength_cache
from world_sim.strength_cache import strength_cache_scope
from .sim_utils import quick_resolve_match

rng = get_rng()
LOG = logging.getLogger(__name__)


def _prompt(io: IOInterface | None, prompt: str, default: str = "") -> str:
    """Use provided IO surface when available to avoid raw input traps."""

    if io:
        return io.prompt(prompt)
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return default

def generate_balanced_bracket(schools):
    """
    Organizes schools into a standard single-elimination bracket.
    Handles byes by giving them to top prestige schools.
    """
    n = len(schools)
    if n < 2: return schools # No bracket needed
    
    # Next power of 2 (e.g., if 6 teams, need 8 slots)
    power_of_2 = 2**math.ceil(math.log2(n))
    byes = power_of_2 - n
    
    # Sort by Prestige (Top seeds get byes)
    sorted_schools = sorted(schools, key=lambda s: s.prestige, reverse=True)
    
    # The top 'byes' schools advance automatically to Round 2
    advanced_schools = sorted_schools[:byes]
    first_round_schools = sorted_schools[byes:]
    
    # Shuffle first round matchups for randomness
    rng.shuffle(first_round_schools)
    
    return first_round_schools, advanced_schools

def run_district_tournament(
    session,
    district_name,
    user_school_id,
    context=None,
    *,
    io: IOInterface | None = None,
    events: Optional[List[Dict[str, object]]] = None,
):
    """
    Runs a full qualifier tournament for a specific district.
    Returns the Winning School.
    """
    with strength_cache_scope() as cache:
        clear_strength_cache(cache)
        log_event("district_tournament_start", district=district_name)
        # 1. Get Schools in District
        schools = list(session.query(School).filter_by(prefecture=district_name).yield_per(256))
        strength_map = (
            get_strength_map(
                session,
                school_ids=[sid for s in schools if (sid := getattr(s, "id", None)) is not None],
                cache=cache,
            )
            if schools
            else {}
        )

        if len(schools) < 2:
            return schools[0] if schools else None

        log = io.log if io else LOG.info
        log(f"\n--- {district_name.upper()} QUALIFIERS ({len(schools)} Schools) ---")
        if events is not None:
            events.append({"type": "tournament_intro", "district": district_name, "schools": len(schools)})

        # 2. Bracket Generation
        current_round, bye_teams = generate_balanced_bracket(schools)
        round_num = 1

        # If we have teams playing in Round 1
        while len(current_round) > 1 or (len(current_round) == 0 and len(bye_teams) > 1):
            # Merge byes back in for Round 2+
            if round_num == 2:
                current_round.extend(bye_teams)
                rng.shuffle(current_round)
                bye_teams = []

            next_round = []

            # Pair up
            matchups = []
            for i in range(0, len(current_round), 2):
                if i + 1 < len(current_round):
                    matchups.append((current_round[i], current_round[i + 1]))
                else:
                    # Odd number logic (shouldn't happen with power of 2 logic, but safety)
                    next_round.append(current_round[i])

            if not matchups and len(next_round) == 1 and round_num > 1:
                # Winner found
                break

            for home, away in matchups:
                # Check if User is involved
                is_user_match = (home.id == user_school_id or away.id == user_school_id)

                if is_user_match:
                    log(f"\nQUALIFIER MATCH: {home.name} vs {away.name}")
                    _prompt(io, "   Press Enter to play...")
                    rival_ctx = context.get_temp_effect("rival_match_context") if context else None
                    rival_presentation = context.get_temp_effect("rival_presentation") if context else None
                    listeners = getattr(context, "match_event_listeners", None) if context else None
                    winner, score = resolve_match(
                        home,
                        away,
                        f"{district_name} Round {round_num}",
                        mode="standard",
                        silent=False,
                        rival_match_context=rival_ctx,
                        rival_presentation=rival_presentation,
                        session=session,
                        event_listeners=listeners,
                    )

                    outcome = "win" if winner.id == user_school_id else "loss"
                    log(f"   Result: {home.name} vs {away.name} -> {score} ({outcome.upper()})")
                    if events is not None:
                        events.append(
                            {
                                "type": "user_match",
                                "district": district_name,
                                "round": round_num,
                                "home": getattr(home, "id", None),
                                "away": getattr(away, "id", None),
                                "winner": getattr(winner, "id", None),
                                "score": score,
                                "outcome": outcome,
                            }
                        )
                else:
                    winner, score, upset, *_meta = quick_resolve_match(
                        session, home, away, strength_map=strength_map, cache=cache
                    )

                log_event(
                    "district_match_resolved",
                    district=district_name,
                    round=round_num,
                    home_id=getattr(home, "id", None),
                    away_id=getattr(away, "id", None),
                    winner_id=getattr(winner, "id", None),
                    score=score,
                    user_match=is_user_match,
                    upset=bool(locals().get("upset", False)),
                )

                next_round.append(winner)

            current_round = next_round
            # Refresh strength map each round to reflect roster/stat changes from resolved games.
            strength_map = (
                get_strength_map(
                    session,
                    school_ids=[sid for s in current_round if (sid := getattr(s, "id", None)) is not None],
                    cache=cache,
                )
                if current_round
                else {}
            )
            round_num += 1

        champion = current_round[0]
        if events is not None and champion:
            events.append({"type": "district_champion", "district": district_name, "champion": getattr(champion, "id", None)})
        log_event("district_tournament_complete", district=district_name, champion_id=getattr(champion, "id", None))
        return champion

def run_season_qualifiers(
    session,
    user_school_id,
    context=None,
    *,
    io: IOInterface | None = None,
    events: Optional[List[Dict[str, object]]] = None,
):
    """
    Runs qualifiers for EVERY district in Japan to determine Koshien participants.
    Returns a list of School objects (The 49 Representatives).
    """

    logger = io.log if io else LOG.info

    prefectures = [r[0] for r in session.query(School.prefecture).distinct()]
    user_school = session.get(School, user_school_id) if user_school_id != -1 else None

    koshien_reps = []

    logger(f"\n=== SUMMER KOSHIEN QUALIFIERS BEGIN ===")
    logger(f"Districts to simulate: {len(prefectures)}")
    log_event("qualifiers_start", count=len(prefectures))
    if events is not None:
        events.append({"type": "qualifiers_start", "count": len(prefectures)})

    for pref in prefectures:
        is_user_pref = user_school and (user_school.prefecture == pref)

        if is_user_pref:
            champ = run_district_tournament(session, pref, user_school_id, context=context, io=io, events=events)
        else:
            champ = run_district_tournament(session, pref, -1, context=context, io=io, events=events)

        koshien_reps.append(champ)

    logger(f"\nQUALIFIERS COMPLETE. 49 SCHOOLS ADVANCE.")
    if events is not None:
        events.append({"type": "qualifiers_complete", "qualifiers": [getattr(rep, "id", None) for rep in koshien_reps]})
    return koshien_reps