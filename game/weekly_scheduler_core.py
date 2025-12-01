from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

from database.setup_db import Team
from game.training_logic import apply_scheduled_action
from game.game_context import GameContext


DAYS_OF_WEEK = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
SLOTS = ['Morning', 'Afternoon', 'Evening']


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

    from match_engine import sim_match  # Local import avoids circular dependency

    my_team = session.get(Team, context.school_id)
    if not my_team:
        raise ValueError("Active team not found for current player.")

    slot_results: List[SlotResult] = []
    warnings: List[str] = []

    for d_idx, day_slots in enumerate(schedule_grid):
        for s_idx, action in enumerate(day_slots):
            if not action:
                continue

            try:
                action_result = apply_scheduled_action(context, action)
                summary = action_result.get("message", "Done.")
                slot_result = SlotResult(
                    day_index=d_idx,
                    slot_index=s_idx,
                    action=action,
                    training_summary=summary,
                )
                slot_result.training_details = action_result

                if 'match' in action and 'b_team' not in action:
                    opponents = session.query(Team).filter(Team.id != context.school_id).all()
                    if not opponents:
                        slot_result.error = "No opponents available for practice match."
                    else:
                        opponent = random.choice(opponents)
                        slot_result.opponent_name = opponent.name
                        winner, score = sim_match(
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
            except Exception as exc:  # Capture errors per-slot to continue week
                warnings.append(
                    f"Error running {action} on {DAYS_OF_WEEK[d_idx]} {SLOTS[s_idx]}: {exc}"
                )

    session.expire_all()
    return ScheduleExecution(results=slot_results, warnings=warnings)
