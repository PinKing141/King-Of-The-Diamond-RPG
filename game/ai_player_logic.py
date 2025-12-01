"""AI progression helpers for seasonal skill acquisition."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session, selectinload

from database.setup_db import GameState, Player, School
from game.player_progression import MilestoneUnlockResult, process_milestone_unlocks
from game.rng import get_rng
from game.skill_system import check_and_grant_skills
from game.trait_logic import ai_skill_unlock_probability, get_progression_speed_multiplier

logger = logging.getLogger(__name__)
PROGRESSION_DEBUG = os.getenv("PROGRESSION_DEBUG", "").lower() in {"1", "true", "yes"}

rng = get_rng()

PITCHER_STATS = ["velocity", "control", "movement", "stamina", "mental"]
BATTER_STATS = ["contact", "power", "speed", "discipline", "clutch"]


@dataclass(frozen=True)
class SkillUnlockRecord:
    school_id: int
    player_id: int
    skill_names: List[str]
    cycle_label: str
    milestones: List[MilestoneUnlockResult] = field(default_factory=list)


class ProgressionDiagnostics:
    """Aggregates unlock stats per AI progression cycle."""

    def __init__(self, cycle_label: str):
        self.cycle_label = cycle_label
        self.schools_scanned = 0
        self.players_considered = 0
        self.rolls_attempted = 0
        self.rolls_won = 0
        self.skill_grants = 0
        self.milestone_grants = 0
        self._sample_logs: List[str] = []

    def record_school(self, school: School) -> None:
        self.schools_scanned += 1
        if PROGRESSION_DEBUG:
            self._sample_logs.append(f"Considering school {school.id} ({school.name})")

    def record_player(self, player: Player) -> None:
        self.players_considered += 1
        if PROGRESSION_DEBUG and len(self._sample_logs) < 10:
            self._sample_logs.append(
                f"Examining player {player.id} ({player.name}) overall={player.overall}"
            )

    def record_roll(self, player: Player, chance: float, roll: float, success: bool) -> None:
        self.rolls_attempted += 1
        if success:
            self.rolls_won += 1
        if PROGRESSION_DEBUG:
            logger.info(
                "[%s] Unlock roll for player %s chance=%.3f roll=%.3f -> %s",
                self.cycle_label,
                player.id,
                chance,
                roll,
                "PASS" if success else "FAIL",
            )

    def record_awards(self, skill_count: int, milestone_count: int) -> None:
        self.skill_grants += skill_count
        self.milestone_grants += milestone_count

    def summarize(self) -> None:
        logger.info(
            "[%s] Progression diagnostics: schools=%d players=%d rolls=%d (wins=%d)"
            " skills=%d milestones=%d",
            self.cycle_label,
            self.schools_scanned,
            self.players_considered,
            self.rolls_attempted,
            self.rolls_won,
            self.skill_grants,
            self.milestone_grants,
        )
        if PROGRESSION_DEBUG:
            for entry in self._sample_logs:
                logger.debug(entry)


_ACTIVE_DIAGNOSTICS: Optional[ProgressionDiagnostics] = None


def run_ai_skill_progression(
    session: Session,
    *,
    cycle_label: str = "monthly",
    prestige_floor: int = 45,
    max_unlocks_per_school: int = 2,
    school_ids: Optional[Sequence[int]] = None,
) -> List[SkillUnlockRecord]:
    """Grant skills to AI players to keep the world competitive.

    Returns a list describing who unlocked which skills during this cycle.
    """
    user_school_id = _get_user_school_id(session)
    query = session.query(School).options(selectinload(School.players))
    if school_ids:
        query = query.filter(School.id.in_(list(school_ids)))
    else:
        query = query.filter(School.prestige >= prestige_floor)
    schools = query.all()

    diagnostics = ProgressionDiagnostics(cycle_label)
    global _ACTIVE_DIAGNOSTICS
    previous_diag = _ACTIVE_DIAGNOSTICS
    _ACTIVE_DIAGNOSTICS = diagnostics

    unlocks: List[SkillUnlockRecord] = []
    try:
        for school in schools:
            if school.id == user_school_id:
                continue
            diagnostics.record_school(school)
        awards = 0
        prestige = school.prestige or 0
        # Focus on best players first.
        for player in sorted(school.players, key=_player_value, reverse=True):
            if awards >= max_unlocks_per_school:
                break
            diagnostics.record_player(player)
            if not _should_attempt_unlock(player, prestige):
                continue
            granted = check_and_grant_skills(
                session,
                player,
                probability_hook=ai_skill_unlock_probability,
            )
            milestone_unlocks = process_milestone_unlocks(session, player)
            if milestone_unlocks:
                granted.extend(entry.skill_name for entry in milestone_unlocks)
            if granted:
                awards += 1
                diagnostics.record_awards(len(granted), len(milestone_unlocks))
                unlocks.append(
                    SkillUnlockRecord(
                        school_id=school.id,
                        player_id=player.id,
                        skill_names=granted,
                        cycle_label=cycle_label,
                        milestones=milestone_unlocks,
                    )
                )
    finally:
        diagnostics.summarize()
        _ACTIVE_DIAGNOSTICS = previous_diag

    if unlocks:
        session.commit()
    return unlocks


def _player_value(player: Player) -> float:
    stats = PITCHER_STATS if (getattr(player, "position", "") or "").lower() == "pitcher" else BATTER_STATS
    values = [(getattr(player, stat, 50) or 50) for stat in stats]
    return sum(values) / len(values)


def _should_attempt_unlock(player: Player, school_prestige: int) -> bool:
    # Higher prestige schools and better players get more rolls.
    prestige_bonus = max(0.0, (school_prestige - 40) / 200.0)
    talent_bonus = max(0.0, (_player_value(player) - 65) / 80.0)
    seniority_bonus = 0.05 * max(0, (getattr(player, "year", 1) or 1) - 1)
    fatigue_penalty = 0.0
    if getattr(player, "fatigue", 0) and player.fatigue > 70:
        fatigue_penalty = 0.05

    progression = get_progression_speed_multiplier(player)
    chance = 0.08 + prestige_bonus + talent_bonus + seniority_bonus - fatigue_penalty
    chance *= _clamp_progression_multiplier(progression)
    chance = min(0.65, max(0.02, chance))
    roll = rng.random()
    decision = roll < chance
    if _ACTIVE_DIAGNOSTICS:
        _ACTIVE_DIAGNOSTICS.record_roll(player, chance, roll, decision)
    return decision


def _get_user_school_id(session: Session) -> Optional[int]:
    state = session.query(GameState).first()
    if not state or not state.active_player_id:
        return None
    player = session.get(Player, state.active_player_id)
    return getattr(player, "school_id", None)


def _clamp_progression_multiplier(multiplier: float) -> float:
    return max(0.7, min(1.4, multiplier))
