"""Autumn regional (8-block) simulator feeding Spring Senbatsu invites."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from database.setup_db import School
from ui.ui_display import Colour
from core.rng import get_rng
from world_sim.regions import REGION_MAP, get_region_for_prefecture
from world_sim.sim_utils import calculate_team_strength, quick_resolve_match

rng = get_rng()

# Regions with additional bid for the runner-up in most years.
RUNNER_UP_REGIONS = {"Kanto", "Kinki", "Kyushu"}


def run_autumn_regionals(session, user_school_id: int, context=None) -> List[int]:
    """
    Simulate the Autumn regional (Shuki Chiku) tournaments across the 8 blocks.

    Returns a list of school IDs that earn Spring Senbatsu consideration.
    """

    print(f"\n{Colour.gold}=== AUTUMN REGIONALS: ROAD TO SENBATSU ==={Colour.RESET}")
    spring_ticket_winners: List[int] = []

    region_buckets: Dict[str, List[School]] = {region: [] for region in REGION_MAP}
    schools: Iterable[School] = session.query(School).all()

    for school in schools:
        pref = getattr(school, "prefecture", None) or ""
        region = get_region_for_prefecture(pref)
        if region == "Unknown":
            continue
        region_buckets[region].append(school)

    for region_name, schools_in_region in region_buckets.items():
        if not schools_in_region:
            continue

        entrants = _pick_prefecture_reps(session, schools_in_region)
        if len(entrants) < 2:
            continue

        champion, runner_up = _simulate_block(session, entrants, region_name, user_school_id)
        if champion:
            spring_ticket_winners.append(getattr(champion, "id", None))
        if runner_up and region_name in RUNNER_UP_REGIONS:
            spring_ticket_winners.append(getattr(runner_up, "id", None))

        if champion:
            user_marker = " (YOU)" if getattr(champion, "id", None) == user_school_id else ""
            print(f"   {Colour.CYAN}{region_name} Champion:{Colour.RESET} {champion.name}{user_marker}")
        if runner_up and region_name in RUNNER_UP_REGIONS:
            print(f"   {Colour.dim}{region_name} Runner-Up:{Colour.RESET} {runner_up.name}")

    return [sid for sid in spring_ticket_winners if sid]


def _pick_prefecture_reps(session, schools: Sequence[School]) -> List[School]:
    """Select top two teams per prefecture by strength/prestige."""

    by_pref: Dict[str, List[Tuple[School, int]]] = defaultdict(list)
    for school in schools:
        pref = getattr(school, "prefecture", None) or ""
        strength = calculate_team_strength(session, getattr(school, "id", None))
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
) -> Tuple[Optional[School], Optional[School]]:
    """Run a single-elimination block; returns (champion, runner_up)."""

    bracket = list(entrants)
    rng.shuffle(bracket)
    runner_up: Optional[School] = None

    while len(bracket) > 1:
        next_round: List[School] = []
        # If odd, give a bye to the strongest remaining team to mirror seeding.
        if len(bracket) % 2 == 1:
            bracket.sort(key=lambda s: calculate_team_strength(session, getattr(s, "id", None)), reverse=True)
            next_round.append(bracket.pop(0))

        for idx in range(0, len(bracket), 2):
            home = bracket[idx]
            away = bracket[idx + 1]
            winner, _score, _upset = quick_resolve_match(session, home, away)
            loser = away if winner is home else home
            next_round.append(winner)
            if len(bracket) == 2:
                runner_up = loser

        bracket = next_round

    champion = bracket[0] if bracket else None
    return champion, runner_up
