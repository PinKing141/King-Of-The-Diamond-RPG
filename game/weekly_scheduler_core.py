from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from database.setup_db import Team
from game.training_logic import apply_scheduled_action
from game.game_context import GameContext


DAYS_OF_WEEK = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
SLOTS = ['Morning', 'Afternoon', 'Evening']

FAST_PRACTICE_MATCHES = os.getenv("FAST_PRACTICE_MATCHES", "").lower() in {"1", "true", "yes"}
PRACTICE_OPPONENT_SAMPLE = int(os.getenv("PRACTICE_OPPONENT_SAMPLE", "0") or 0)


def _pick_practice_opponent(session, school_id: Optional[int]) -> Optional[Team]:
    if school_id is None:
        return None

    base_query = session.query(Team).filter(Team.id != school_id)
    total = base_query.count()
    if total == 0:
        return None

    if PRACTICE_OPPONENT_SAMPLE and PRACTICE_OPPONENT_SAMPLE < total:
        offsets = set()
        while len(offsets) < PRACTICE_OPPONENT_SAMPLE:
            offsets.add(random.randrange(total))
        candidates = []
        for offset in offsets:
            opponent = (
                session.query(Team)
                .filter(Team.id != school_id)
                .offset(offset)
                .limit(1)
                .first()
            )
            if opponent:
                candidates.append(opponent)
        if candidates:
            return random.choice(candidates)

    offset = random.randrange(total)
    return (
        session.query(Team)
        .filter(Team.id != school_id)
        .offset(offset)
        .limit(1)
        .first()
    )


@dataclass
class SlotResult:
    day_index: int
    slot_index: int
    action: str
    training_summary: str
    opponent_name: Optional[str] = None
    match_result: Optional[str] = None
    match_score: Optional[str] = None
    error: Optional[str] = None
    training_details: Optional[dict] = None

    @property
    def day_name(self) -> str:
        return DAYS_OF_WEEK[self.day_index]

    @property
    def slot_name(self) -> str:
        return SLOTS[self.slot_index]


@dataclass
class ScheduleExecution:
    """Aggregate output generated when executing a weekly schedule."""

    results: List[SlotResult]
    warnings: List[str]


def execute_schedule_core(
    context: GameContext,
    schedule_grid,
    current_week: int,
) -> ScheduleExecution:
    """Apply a planned schedule to the database and return structured outcomes."""
    session = context.session
    if context.school_id is None:
        raise ValueError("GameContext missing school_id; cannot execute schedule.")

    from match_engine import sim_match, sim_match_fast  # Local import avoids circular dependency

    my_team = session.get(Team, context.school_id)
    if not my_team:
        raise ValueError("Active team not found for current player.")

    slot_results: List[SlotResult] = []
    warnings: List[str] = []
    progression_state: Dict[str, object] = {}

    for d_idx, day_slots in enumerate(schedule_grid):
        day_dirty = False
        for s_idx, action in enumerate(day_slots):
            if not action:
                continue

            try:
                action_result = apply_scheduled_action(
                    context,
                    action,
                    commit=False,
                    progression_state=progression_state,
                )
                summary = action_result.get("message", "Done.")
                slot_result = SlotResult(
                    day_index=d_idx,
                    slot_index=s_idx,
                    action=action,
                    training_summary=summary,
                )
                slot_result.training_details = action_result

                if 'match' in action and 'b_team' not in action:
                    opponent = _pick_practice_opponent(session, context.school_id)
                    if not opponent:
                        slot_result.error = "No opponents available for practice match."
                    else:
                        slot_result.opponent_name = opponent.name
                        sim_runner = sim_match_fast if FAST_PRACTICE_MATCHES else sim_match
                        winner, score = sim_runner(
                            my_team,
                            opponent,
                            tournament_name="Practice Match",
                            silent=False,
                        )
                        if winner:
                            outcome = 'WON' if winner.id == my_team.id else 'LOST'
                            slot_result.match_result = outcome
                            slot_result.match_score = score
                        else:
                            slot_result.match_result = "UNKNOWN"
                slot_results.append(slot_result)
                day_dirty = True
            except Exception as exc:  # Capture errors per-slot to continue week
                session.rollback()
                warnings.append(
                    f"Error running {action} on {DAYS_OF_WEEK[d_idx]} {SLOTS[s_idx]}: {exc}"
                )

        if day_dirty:
            session.commit()

    session.expire_all()
    return ScheduleExecution(results=slot_results, warnings=warnings)
