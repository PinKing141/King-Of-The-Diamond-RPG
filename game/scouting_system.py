from dataclasses import dataclass
from typing import Optional

from database.setup_db import School, ScoutingData, get_session

MAX_KNOWLEDGE_LEVEL = 3


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
    cost_yen: int = 50000,
) -> ScoutingActionResult:
    """Attempt to scout a team using the provided session."""
    user = session.get(School, user_school_id)
    target = session.get(School, target_school_id)
    user_budget = user.budget if user else None
    target_id = target.id if target else target_school_id

    if not user or not target:
        return ScoutingActionResult(
            success=False,
            status="invalid-selection",
            target_school_id=target_id,
            cost_yen=cost_yen,
            knowledge_before=None,
            knowledge_after=None,
            budget_before=user_budget,
            budget_after=user_budget,
        )

    scout_data = session.get(ScoutingData, target.id)
    if not scout_data:
        scout_data = ScoutingData(school_id=target.id, knowledge_level=0, rivalry_score=0)
        session.add(scout_data)

    knowledge_before = scout_data.knowledge_level

    if user.budget < cost_yen:
        return ScoutingActionResult(
            success=False,
            status="insufficient-funds",
            target_school_id=target.id,
            cost_yen=cost_yen,
            knowledge_before=knowledge_before,
            knowledge_after=knowledge_before,
            budget_before=user.budget,
            budget_after=user.budget,
        )

    if scout_data.knowledge_level >= MAX_KNOWLEDGE_LEVEL:
        return ScoutingActionResult(
            success=False,
            status="max-knowledge",
            target_school_id=target.id,
            cost_yen=cost_yen,
            knowledge_before=knowledge_before,
            knowledge_after=knowledge_before,
            budget_before=user.budget,
            budget_after=user.budget,
        )

    user.budget -= cost_yen
    scout_data.knowledge_level += 1

    session.commit()
    session.refresh(user)
    session.refresh(scout_data)

    return ScoutingActionResult(
        success=True,
        status="success",
        target_school_id=target.id,
        cost_yen=cost_yen,
        knowledge_before=knowledge_before,
        knowledge_after=scout_data.knowledge_level,
        budget_before=user.budget + cost_yen,
        budget_after=user.budget,
    )