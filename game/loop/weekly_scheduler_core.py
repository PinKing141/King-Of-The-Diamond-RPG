from __future__ import annotations

import os
import random
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError

from database.setup_db import Team
from core.game_context import GameContext
from game.services.training_service import TrainingService
from game.services.training_domain import apply_training_action_dto
from core.repositories import PlayerRepository, TeamRepository
from game.services.progression_port import ProgressionPort

logger = logging.getLogger(__name__)


DAYS_OF_WEEK = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
SLOTS = ['Morning', 'Afternoon', 'Evening']

FAST_PRACTICE_MATCHES = os.getenv("FAST_PRACTICE_MATCHES", "").lower() in {"1", "true", "yes"}
PRACTICE_OPPONENT_SAMPLE = int(os.getenv("PRACTICE_OPPONENT_SAMPLE", "0") or 0)


def _pick_practice_opponent(session, school_id: Optional[int], *, rng: Optional[random.Random] = None) -> Optional[Team]:
    if school_id is None:
        return None

    rng = rng or random

    base_query = session.query(Team).filter(Team.id != school_id)
    total = base_query.count()
    if total == 0:
        return None

    if PRACTICE_OPPONENT_SAMPLE and PRACTICE_OPPONENT_SAMPLE < total:
        offsets = set()
        while len(offsets) < PRACTICE_OPPONENT_SAMPLE:
            offsets.add(rng.randrange(total))
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
            return rng.choice(candidates)

    offset = rng.randrange(total)
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
    headlines: List[str]


@dataclass
class WeekSummary:
    """Aggregated post-week view consumed by UI, analytics, and auto-play."""

    week_number: int
    stat_gains: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    xp_gains: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    events_triggered: List[str] = field(default_factory=list)
    match_outcomes: List[Dict[str, str]] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    schedule_notes: List[str] = field(default_factory=list)
    stopped_by_interrupt: bool = False
    interrupt_reasons: List[str] = field(default_factory=list)
    newsletter: List[str] = field(default_factory=list)

    def record_slot(self, result: SlotResult) -> None:
        details = result.training_details or {}
        for stat, delta in (details.get("stat_changes") or {}).items():
            self.stat_gains[stat] += delta
        for stat, delta in (details.get("xp_gains") or {}).items():
            self.xp_gains[stat] += delta
        for pitch, delta in (details.get("mastery_gains") or {}).items():
            self.xp_gains[f"mastery:{pitch}"] += delta

        if details.get("skills_unlocked"):
            for skill in details["skills_unlocked"]:
                self.highlights.append(f"Unlocked skill: {skill}")
        if details.get("breakthrough"):
            stat = details["breakthrough"].get("stat", "Unknown").replace('_', ' ').title()
            self.highlights.append(f"Breakthrough in {stat}")
        milestones = details.get("milestones") or []
        for entry in milestones:
            label = getattr(entry, "milestone_label", None) or getattr(entry, "milestone_key", "Milestone")
            reward = getattr(entry, "skill_name", "")
            reward_suffix = f" -> {reward}" if reward else ""
            self.highlights.append(f"Milestone: {label}{reward_suffix}")

        if result.match_result:
            self.match_outcomes.append(
                {
                    "slot": f"{result.day_name} {result.slot_name}",
                    "opponent": result.opponent_name or "Opponent",
                    "result": result.match_result,
                    "score": result.match_score or "-",
                }
            )
        if result.error:
            self.add_warning(result.error)

        status = details.get("status")
        if status == "injured":
            self.flag_interrupt(f"Injury during {result.day_name} {result.slot_name}")

    def add_event(self, description: str) -> None:
        if description:
            self.events_triggered.append(description)

    def add_warning(self, warning: str) -> None:
        if warning:
            self.warnings.append(warning)

    def add_schedule_note(self, note: str) -> None:
        if note:
            self.schedule_notes.append(note)

    def flag_interrupt(self, reason: str) -> None:
        self.stopped_by_interrupt = True
        if reason:
            self.interrupt_reasons.append(reason)

    def build_newsletter(self, *, team_name: str) -> List[str]:
        if self.newsletter:
            return self.newsletter
        lines: List[str] = []
        for entry in self.match_outcomes:
            slot = entry.get("slot", "Match")
            opponent = entry.get("opponent", "Opponent")
            result = entry.get("result", "?")
            score = entry.get("score", "-")
            prefix = "Upset Alert: " if result.upper() == "WON" else "Setback: "
            lines.append(f"{prefix}{team_name} {result} vs {opponent} ({score}) in {slot}.")
        if self.highlights:
            lines.append(self.highlights[0])
        if self.warnings:
            lines.append(self.warnings[0])
        self.newsletter = lines[:4]
        return self.newsletter

    def to_payload(self) -> Dict[str, object]:
        return {
            "week": self.week_number,
            "stat_gains": dict(self.stat_gains),
            "xp_gains": dict(self.xp_gains),
            "events": list(self.events_triggered),
            "matches": list(self.match_outcomes),
            "highlights": list(self.highlights),
            "warnings": list(self.warnings),
            "schedule_notes": list(self.schedule_notes),
            "stopped": self.stopped_by_interrupt,
            "reasons": list(self.interrupt_reasons),
        }


def execute_schedule_core(
    context: GameContext,
    schedule_grid,
    current_week: int,
    *,
    training_service: Optional[TrainingService] = None,
    rng_seed: Optional[int] = None,
    player_repo: Optional[PlayerRepository] = None,
    team_repo: Optional[TeamRepository] = None,
    progression_service: Optional[ProgressionPort] = None,
) -> ScheduleExecution:
    """Apply a planned schedule to the database and return structured outcomes."""
    session = context.session
    if context.school_id is None:
        raise ValueError("GameContext missing school_id; cannot execute schedule.")

        from match_engine.resolver import resolve_match  # Local import avoids circular dependency

    my_team = session.get(Team, context.school_id) if session else None
    if session and not my_team:
        raise ValueError("Active team not found for current player.")

    slot_results: List[SlotResult] = []
    warnings: List[str] = []
    headlines: List[str] = []
    progression_state: Dict[str, object] = {}

    service = training_service or TrainingService.with_seed(rng_seed)
    rng = service.rng

    player_dto = None
    if player_repo is not None:
        player_dto = player_repo.get_active_player()
        if player_dto is None:
            raise ValueError("Active player not found via repository.")

    for d_idx, day_slots in enumerate(schedule_grid):
        day_dirty = False
        for s_idx, action in enumerate(day_slots):
            if not action:
                continue

            try:
                if player_dto is not None:
                    result = apply_training_action_dto(
                        player_dto,
                        action,
                        rng=rng,
                        progression_service=progression_service,
                        progression_state=progression_state,
                    )
                    player_dto = result.dto
                    action_result = {
                        "status": "ok",
                        "message": result.summary,
                        "fatigue_change": result.fatigue_change,
                        "stat_changes": result.stat_changes,
                        "xp_gains": result.xp_gains,
                        "mastery_gains": result.mastery_gains,
                        "breakthrough": result.breakthrough,
                        "new_fatigue": player_dto.fatigue,
                        "skills_unlocked": result.skills_unlocked,
                        "milestones": result.milestones,
                    }
                    player_repo.save_player(player_dto)
                else:
                    action_result = service.apply_action(
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

                if 'match' in action and 'b_team' not in action and session:
                    opponent = _pick_practice_opponent(session, context.school_id, rng=rng)
                    if not opponent:
                        slot_result.error = "No opponents available for practice match."
                    else:
                        slot_result.opponent_name = opponent.name
                        mode = "fast" if FAST_PRACTICE_MATCHES else "standard"
                        listeners = getattr(context, "match_event_listeners", None) if context else None
                        winner, score = resolve_match(
                            my_team,
                            opponent,
                            tournament_name="Practice Match",
                            mode=mode,
                            silent=False,
                            rival_match_context=context.get_temp_effect("rival_match_context") if context else None,
                            session=session,
                            event_listeners=listeners,
                        )
                        if winner:
                            outcome = 'WON' if winner.id == my_team.id else 'LOST'
                            slot_result.match_result = outcome
                            slot_result.match_score = score
                            headline = f"{my_team.name} {outcome} vs {opponent.name if opponent else 'Opponent'} ({score})"
                            if outcome == "WON" and getattr(opponent, "prestige", 0) > getattr(my_team, "prestige", 0) + 12:
                                headline = "Dark Horse Alert: " + headline
                            headlines.append(headline)
                        else:
                            slot_result.match_result = "UNKNOWN"
                slot_results.append(slot_result)
                day_dirty = True
            except (SQLAlchemyError, ValueError, TypeError, RuntimeError) as exc:  # Capture expected per-slot issues
                session.rollback()
                warnings.append(
                    f"Error running {action} on {DAYS_OF_WEEK[d_idx]} {SLOTS[s_idx]}: {exc}"
                )

        if day_dirty:
            session.commit()

    session.expire_all()
    return ScheduleExecution(results=slot_results, warnings=warnings, headlines=headlines)
