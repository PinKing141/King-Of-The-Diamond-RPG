import json
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

PREFECTURE_REGION = {
    "Hokkaido": "Hokkaido",
    "Aomori": "Tohoku",
    "Iwate": "Tohoku",
    "Miyagi": "Tohoku",
    "Akita": "Tohoku",
    "Yamagata": "Tohoku",
    "Fukushima": "Tohoku",
    "Ibaraki": "Kanto",
    "Tochigi": "Kanto",
    "Gunma": "Kanto",
    "Saitama": "Kanto",
    "Chiba": "Kanto",
    "Tokyo": "Kanto",
    "Kanagawa": "Kanto",
    "Niigata": "Chubu",
    "Toyama": "Chubu",
    "Ishikawa": "Chubu",
    "Fukui": "Chubu",
    "Yamanashi": "Chubu",
    "Nagano": "Chubu",
    "Gifu": "Chubu",
    "Shizuoka": "Chubu",
    "Aichi": "Chubu",
    "Mie": "Kansai",
    "Shiga": "Kansai",
    "Kyoto": "Kansai",
    "Osaka": "Kansai",
    "Hyogo": "Kansai",
    "Nara": "Kansai",
    "Wakayama": "Kansai",
    "Tottori": "Chugoku",
    "Shimane": "Chugoku",
    "Okayama": "Chugoku",
    "Hiroshima": "Chugoku",
    "Yamaguchi": "Chugoku",
    "Tokushima": "Shikoku",
    "Kagawa": "Shikoku",
    "Ehime": "Shikoku",
    "Kochi": "Shikoku",
    "Fukuoka": "Kyushu",
    "Saga": "Kyushu",
    "Nagasaki": "Kyushu",
    "Kumamoto": "Kyushu",
    "Oita": "Kyushu",
    "Miyazaki": "Kyushu",
    "Kagoshima": "Kyushu",
    "Okinawa": "Kyushu",
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
    network_scope: Optional[str] = None
    network_rating: Optional[int] = None


def _decode_network(payload) -> dict:
    if not payload:
        return {}
    if isinstance(payload, dict):
        return payload
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return {}


def _pref_region(prefecture: Optional[str]) -> str:
    if not prefecture:
        return "Unknown"
    return PREFECTURE_REGION.get(prefecture, "Unknown")


def _scouting_scope(user: Optional[School], target: Optional[School]) -> str:
    if not user or not target:
        return "National"
    if getattr(user, 'geo_location_id', None) and user.geo_location_id == getattr(target, 'geo_location_id', None):
        return "Local"
    if user.prefecture and target.prefecture and user.prefecture == target.prefecture:
        return "Local"
    if _pref_region(user.prefecture) == _pref_region(target.prefecture):
        return "Regional"
    if target.prefecture:
        return "National"
    return "International"


def _network_modifiers(user: Optional[School], target: Optional[School]):
    scope = _scouting_scope(user, target)
    network = _decode_network(getattr(user, 'scouting_network', None) if user else None)
    rating = network.get(scope)
    fallback_keys = ("National", "Regional", "Local", "International")
    if rating is None:
        for key in fallback_keys:
            if key in network:
                rating = network[key]
                break
    rating = rating if rating is not None else 50
    rating = max(25.0, min(95.0, float(rating)))
    reach_delta = (rating - 50.0) / 50.0
    cost_multiplier = max(0.65, min(1.25, 1.0 - reach_delta * 0.25))
    knowledge_multiplier = max(0.75, min(1.4, 1.0 + reach_delta * 0.35))
    recruit_bonus = 1 if rating >= 80 else 0
    return scope, int(round(rating)), cost_multiplier, knowledge_multiplier, recruit_bonus


def describe_network_advantage(user: Optional[School], target: Optional[School]) -> dict:
    """Return a structured preview of scouting reach modifiers for UI/telemetry."""
    scope, rating, cost_mult, knowledge_mult, recruit_bonus = _network_modifiers(user, target)
    return {
        "scope": scope,
        "rating": rating,
        "cost_multiplier": round(cost_mult, 2),
        "knowledge_multiplier": round(knowledge_mult, 2),
        "recruit_bonus": recruit_bonus,
    }


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
    scope_label = None
    network_rating = None

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
            network_scope=scope_label,
            network_rating=network_rating,
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
            network_scope=scope_label,
            network_rating=network_rating,
        )

    scope_label, network_rating, cost_multiplier, knowledge_multiplier, network_recruit_bonus = _network_modifiers(user, target)
    package_cost = max(1, int(round(package_cost * cost_multiplier)))
    knowledge_gain = max(1, int(round(knowledge_gain * knowledge_multiplier)))
    recruit_bonus += network_recruit_bonus

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
            network_scope=scope_label,
            network_rating=network_rating,
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
            network_scope=scope_label,
            network_rating=network_rating,
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
            network_scope=scope_label,
            network_rating=network_rating,
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
        network_scope=scope_label,
        network_rating=network_rating,
    )