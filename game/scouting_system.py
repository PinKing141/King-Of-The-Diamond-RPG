from dataclasses import dataclass
from typing import Optional

from database.setup_db import School, ScoutingData, get_session

MAX_KNOWLEDGE_LEVEL = 3

# Yen costs and benefits for each scouting package tier.
SCOUTING_PACKAGES = {
    "basic": {"cost": 40000, "knowledge_gain": 1, "recruit_roll_bonus": 0},
    "advanced": {"cost": 80000, "knowledge_gain": 2, "recruit_roll_bonus": 1},
    "elite": {"cost": 150000, "knowledge_gain": 3, "recruit_roll_bonus": 2},
}


@dataclass(frozen=True)
class ScoutingInfoData:
    school_id: int
    knowledge_level: int
    rivalry_score: int


@dataclass(frozen=True)
class ScoutingActionResult:
    success: bool
    status: str
    target_school_id: Optional[int]
    cost_yen: int
    knowledge_before: Optional[int]
    knowledge_after: Optional[int]
    budget_before: Optional[int]
    budget_after: Optional[int]
    tier: Optional[str] = None
    knowledge_gained: int = 0
    recruit_roll_bonus: int = 0


def get_scouting_info(school_id: int, session=None) -> ScoutingInfoData:
    """Retrieve or create scouting record for a target school."""
    owns_session = session is None
    if owns_session:
        session = get_session()

    try:
        info = session.get(ScoutingData, school_id)

        if not info:
            info = ScoutingData(school_id=school_id, knowledge_level=0, rivalry_score=0)
            session.add(info)
            session.commit()

        session.refresh(info)
        return ScoutingInfoData(
            school_id=info.school_id,
            knowledge_level=info.knowledge_level,
            rivalry_score=info.rivalry_score,
        )
    finally:
        if owns_session:
            session.close()


def perform_scout_action(
    session,
    user_school_id: int,
    target_school_id: int,
    cost_yen: Optional[int] = None,
    tier: str = "basic",
) -> ScoutingActionResult:
    """Attempt to scout a team using the provided session."""
    tier_key = (tier or "basic").lower()
    package = SCOUTING_PACKAGES.get(tier_key)

    user = session.get(School, user_school_id)
    target = session.get(School, target_school_id)
    user_budget = user.budget if user else None
    target_id = target.id if target else target_school_id

    if not package:
        return ScoutingActionResult(
            success=False,
            status="invalid-tier",
            target_school_id=target_id,
            cost_yen=0,
            knowledge_before=None,
            knowledge_after=None,
            budget_before=user_budget,
            budget_after=user_budget,
            tier=tier,
        )

    package_cost = cost_yen if cost_yen is not None else package["cost"]
    knowledge_gain = package["knowledge_gain"]
    recruit_bonus = package["recruit_roll_bonus"]

    if not user or not target:
        return ScoutingActionResult(
            success=False,
            status="invalid-selection",
            target_school_id=target_id,
            cost_yen=package_cost,
            knowledge_before=None,
            knowledge_after=None,
            budget_before=user_budget,
            budget_after=user_budget,
            tier=tier_key,
        )

    scout_data = session.get(ScoutingData, target.id)
    if not scout_data:
        scout_data = ScoutingData(school_id=target.id, knowledge_level=0, rivalry_score=0)
        session.add(scout_data)

    knowledge_before = scout_data.knowledge_level

    if user.budget < package_cost:
        return ScoutingActionResult(
            success=False,
            status="insufficient-funds",
            target_school_id=target.id,
            cost_yen=package_cost,
            knowledge_before=knowledge_before,
            knowledge_after=knowledge_before,
            budget_before=user.budget,
            budget_after=user.budget,
            tier=tier_key,
        )

    if scout_data.knowledge_level >= MAX_KNOWLEDGE_LEVEL:
        return ScoutingActionResult(
            success=False,
            status="max-knowledge",
            target_school_id=target.id,
            cost_yen=package_cost,
            knowledge_before=knowledge_before,
            knowledge_after=knowledge_before,
            budget_before=user.budget,
            budget_after=user.budget,
            tier=tier_key,
        )

    knowledge_after = min(
        MAX_KNOWLEDGE_LEVEL,
        scout_data.knowledge_level + max(1, knowledge_gain),
    )
    applied_gain = knowledge_after - scout_data.knowledge_level

    if applied_gain <= 0:
        return ScoutingActionResult(
            success=False,
            status="max-knowledge",
            target_school_id=target.id,
            cost_yen=package_cost,
            knowledge_before=knowledge_before,
            knowledge_after=knowledge_before,
            budget_before=user.budget,
            budget_after=user.budget,
            tier=tier_key,
        )

    starting_budget = user.budget
    user.budget -= package_cost
    scout_data.knowledge_level = knowledge_after

    session.commit()
    session.refresh(user)
    session.refresh(scout_data)

    return ScoutingActionResult(
        success=True,
        status="success",
        target_school_id=target.id,
        cost_yen=package_cost,
        knowledge_before=knowledge_before,
        knowledge_after=scout_data.knowledge_level,
        budget_before=starting_budget,
        budget_after=user.budget,
        tier=tier_key,
        knowledge_gained=applied_gain,
        recruit_roll_bonus=recruit_bonus,
    )