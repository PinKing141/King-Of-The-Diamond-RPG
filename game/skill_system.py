"""Skill definitions and acquisition helpers."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import logging
import os
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from database.setup_db import Player, PlayerSkill
from game.rng import get_rng
from game.trait_catalog import SKILL_DEFINITIONS
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
PROGRESSION_DEBUG = os.getenv("PROGRESSION_DEBUG", "").lower() in {"1", "true", "yes"}
_SKILL_RNG = get_rng()

# ---------------------------------------------------------------------------
# Skill catalog
# ---------------------------------------------------------------------------
"""
Legacy inline skill catalog retained for reference.

SKILL_DEFINITIONS: Dict[str, Dict] = {
    "clutch_hitter": {
        "name": "Clutch Hitter",
        "description": "Locks in when the tying run is aboard late in games.",
        "requirements": [
            {"stat": "contact", "min": 50},
            {"stat": "power", "min": 55},
            {"stat": "clutch", "min": 70},
        ],
        "type": "situational",
        "condition": "late_inning_pressure",
        "modifiers": {"contact": 12, "power": 10},
        "alignment": "positive",
    },
    "power_hitter": {
        "name": "Power Hitter",
        "description": "Leverages max-effort hacks for effortless carry.",
        "requirements": [
            {"stat": "power", "min": 60},
            {"stat": "contact", "min": 40},
        ],
        "type": "passive_buff",
        "modifiers": {"power": 10, "contact": -4},
        "alignment": "positive",
    },
    "mental_wall": {
        "name": "Mental Wall",
        "description": "Confidence dips barely register thanks to elite focus.",
        "requirements": [
            {"stat": "mental", "min": 72},
            {"stat": "discipline", "min": 65},
            {"stat": "volatility", "max": 35},
        ],
        "type": "situational",
        "condition": "high_pressure_moment",
        "modifiers": {"mental": 8, "discipline": 6, "clutch": 6},
        "alignment": "positive",
    },
    "high_heat": {
        "name": "High Heat",
        "description": "Lives at the letters with overpowering velo.",
        "requirements": [
            {"stat": "position", "equals": "Pitcher"},
            {"stat": "velocity", "min": 135},
        ],
        "type": "passive_buff",
        "modifiers": {"velocity": 4, "control": -3},
        "alignment": "positive",
    },
    "bunt_master": {
        "name": "Bunt Master",
        "description": "Small-ball execution is second nature.",
        "requirements": [
            {"stat": "contact", "min": 45},
            {"stat": "discipline", "min": 58},
            {"stat": "speed", "min": 50},
        ],
    },
    "speed_demon": {
        "name": "Speed Demon",
        "description": "Elite speedster with instincts on the bases.",
        "requirements": [
            {"stat": "speed", "min": 55},
            {"stat": "discipline", "min": 53},
        ],
    },
    "power_surge": {
        "name": "Power Surge",
        "description": "Home run power that ignites once warm.",
        "requirements": [
            {"stat": "power", "min": 60},
            {"stat": "contact", "min": 48},
        ],
    },
    "control_freak": {
        "name": "Control Freak",
        "description": "Pinpoint command regardless of the count.",
        "requirements": [
            {"stat": "position", "equals": "Pitcher"},
            {"stat": "control", "min": 55},
            {"stat": "volatility", "max": 40},
        ],
    },
    "iron_will": {
        "name": "Iron Will",
        "description": "Never-say-die mentality that shrugs off adversity.",
        "requirements": [
            {"stat": "mental", "min": 65},
            {"stat": "drive", "min": 65},
            {"stat": "morale", "min": 60},
        ],
    },
    "workhorse": {
        "name": "Workhorse",
        "description": "Built to carry deep outings every week.",
        "requirements": [
            {"stat": "position", "equals": "Pitcher"},
            {"stat": "stamina", "min": 60},
        ],
        "type": "passive_buff",
        "modifiers": {"stamina": 5},
        "roll_modifiers": {"fatigue": -0.2, "injury": -0.08},
        "alignment": "positive",
    },
    "flame_thrower": {
        "name": "Flame Thrower",
        "description": "Triple-digit heater that overwhelms hitters.",
        "requirements": [
            {"stat": "position", "equals": "Pitcher"},
            {"stat": "velocity", "min": 132},
            {"stat": "control", "min": 55},
        ],
    },
    "shutdown_closer": {
        "name": "Shutdown Closer",
        "description": "Cold blood in the ninth inning.",
        "requirements": [
            {"stat": "position", "equals": "Pitcher"},
            {"stat": "role", "equals_any": ["CLOSER", "RELIEVER"]},
            {"stat": "clutch", "min": 70},
            {"stat": "volatility", "max": 45},
        ],
    },
    "defensive_anchor": {
        "name": "Defensive Anchor",
        "description": "Locks down the hot corner with elite fielding.",
        "requirements": [
            {"stat": "fielding", "min": 58},
            {"stat": "throwing", "min": 65},
        ],
    },
    "field_general": {
        "name": "Field General",
        "description": "Catcher with steady leadership and pitch calling.",
        "requirements": [
            {"stat": "position", "equals": "Catcher"},
            {"stat": "command", "min": 60},
            {"stat": "discipline", "min": 60},
        ],
    },
    "spark_plug": {
        "name": "Spark Plug",
        "description": "Brings relentless energy to every dugout.",
        "requirements": [
            {"stat": "speed", "min": 55},
            {"stat": "drive", "min": 60},
            {"stat": "morale", "min": 60},
        ],
    },
    "situational_ace": {
        "name": "Situational Ace",
        "description": "Thrives when the bullpen phone rings late.",
        "requirements": [
            {"stat": "position", "equals": "Pitcher"},
            {"stat": "command", "min": 58},
            {"stat": "clutch", "min": 68},
        ],
    },
    "gap_specialist": {
        "name": "Gap Specialist",
        "description": "Doubles machine with spray-chart mastery.",
        "requirements": [
            {"stat": "contact", "min": 48},
            {"stat": "power", "min": 45, "max": 72},
        ],
    },
    "contact_artist": {
        "name": "Contact Artist",
        "description": "Almost never whiffs and lives on the barrel.",
        "requirements": [
            {"stat": "contact", "min": 52},
            {"stat": "discipline", "min": 65},
        ],
    },
    "strikeout_artist": {
        "name": "Strikeout Artist",
        "description": "Piles up Ks with raw stuff and deception.",
        "requirements": [
            {"stat": "position", "equals": "Pitcher"},
            {"stat": "velocity", "min": 130},
            {"stat": "movement", "min": 50},
        ],
    },
    "sniper_arm": {
        "name": "Sniper Arm",
        "description": "Outfield cannon keeps runners glued to bags.",
        "requirements": [
            {"stat": "throwing", "min": 75},
            {"stat": "fielding", "min": 55},
        ],
    },
    "glass_cannon": {
        "name": "Glass Cannon",
        "description": "Explosive output but body breaks down quickly.",
        "requirements": [
            {"stat": "power", "min": 60},
            {"stat": "stamina", "max": 48},
        ],
        "type": "passive_debuff",
        "modifiers": {"power": 6, "stamina": -6},
        "roll_modifiers": {"fatigue": 0.18, "injury": 0.22},
        "alignment": "negative",
    },
    "pickoff_specialist": {
        "name": "Pickoff Specialist",
        "description": "Neutralizes running games with lightning moves.",
        "requirements": [
            {"stat": "position", "equals": "Pitcher"},
            {"stat": "control", "min": 55},
            {"stat": "movement", "min": 48},
        ],
    },
    "choker": {
        "name": "Choker",
        "description": "Presses too hard when the lights burn brightest.",
        "requirements": [],
        "type": "situational",
        "condition": "late_inning_pressure",
        "modifiers": {"contact": -12, "power": -10},
        "alignment": "negative",
        "allow_progression": False,
    },
    "leadoff_catalyst": {
        "name": "Leadoff Catalyst",
        "description": "Electric first batter who sets the tone early.",
        "requirements": [
            {"stat": "speed", "min": 58},
            {"stat": "contact", "min": 50},
        ],
        "type": "situational",
        "condition": "lineup_leadoff",
        "modifiers": {"speed": 8, "contact": 5},
        "alignment": "role",
    },
    "free_swinger": {
        "name": "Free Swinger",
        "description": "Attacks everything, for better or worse.",
        "requirements": [
            {"stat": "discipline", "max": 55},
        ],
        "type": "behavior",
        "ai_tendency": {"swing_aggression": 1.4},
        "alignment": "neutral",
    },
}
"""


# ---------------------------------------------------------------------------
# Acquisition helpers
# ---------------------------------------------------------------------------
def check_and_grant_skills(
    session,
    player,
    *,
    probability_hook: Optional[Callable[[object, str, Dict], float]] = None,
    rng=None,
    owned_keys: Optional[Set[str]] = None,
) -> List[str]:
    """Grant any newly-qualified skills for the provided player.

    Returns a list of human-readable skill names that were unlocked during the check.
    """
    if not player or not player.id:
        return []

    cache = owned_keys if owned_keys is not None else _skill_key_cache(player)
    owned_lookup = cache if owned_keys is not None else set(cache)
    unlocked: List[str] = []

    random_source = rng or _SKILL_RNG

    for key, data in SKILL_DEFINITIONS.items():
        key_lower = key.lower()
        if key_lower in owned_lookup:
            continue
        if not data.get("allow_progression", True):
            continue
        if not _meets_all_requirements(player, data.get("requirements", [])):
            if PROGRESSION_DEBUG:
                reason = _describe_requirement_failure(player, data.get("requirements", []))
                logger.info(
                    "Player %s gating out of %s due to %s",
                    getattr(player, "id", "unknown"),
                    key,
                    reason,
                )
            continue

        chance = 1.0
        if probability_hook:
            try:
                chance = float(probability_hook(player, key_lower, data))
            except Exception:
                chance = 1.0
            chance = max(0.0, min(1.0, chance))
        if chance <= 0.0:
            if PROGRESSION_DEBUG:
                logger.info(
                    "Player %s gating out of %s due to zero probability modifier",
                    getattr(player, "id", "unknown"),
                    key,
                )
            continue
        if chance < 1.0:
            roll = random_source.random()
            if roll > chance:
                if PROGRESSION_DEBUG:
                    logger.info(
                        "Player %s failed probability gate for %s (roll %.3f chance %.2f)",
                        getattr(player, "id", "unknown"),
                        key,
                        roll,
                        chance,
                    )
                continue

        display_name = grant_skill_by_key(session, player, key, owned_cache=cache)
        if display_name:
            owned_lookup.add(key_lower)
            unlocked.append(display_name)
            if PROGRESSION_DEBUG:
                logger.info(
                    "Player %s unlocked %s via stat requirements",
                    getattr(player, "id", "unknown"),
                    display_name,
                )

    if unlocked:
        session.flush()

    return unlocked


def _meets_all_requirements(player, requirements: Sequence[Dict]) -> bool:
    for req in requirements:
        if not _meets_single_requirement(player, req):
            return False
    return True


def _meets_single_requirement(player, requirement: Dict) -> bool:
    stat = requirement.get("stat")
    if not stat:
        return True

    value = getattr(player, stat, None)
    if value is None:
        return False

    equals = requirement.get("equals")
    if equals is not None:
        return str(value).lower() == str(equals).lower()

    equals_any: Iterable = requirement.get("equals_any", [])
    if equals_any:
        compare = str(value).lower()
        options = {str(opt).lower() for opt in equals_any}
        return compare in options

    minimum = requirement.get("min")
    if minimum is not None:
        try:
            if float(value) < float(minimum):
                return False
        except (TypeError, ValueError):
            return False

    maximum = requirement.get("max")
    if maximum is not None:
        try:
            if float(value) > float(maximum):
                return False
        except (TypeError, ValueError):
            return False

    return True


def _skill_key_cache(player) -> Set[str]:
    if not player:
        return set()
    cache = getattr(player, "_skill_key_cache", None)
    if cache is not None:
        return cache
    skills = getattr(player, "skills", None)
    keys: Set[str] = set()
    if skills:
        try:
            for entry in skills:
                key = getattr(entry, "skill_key", None)
                if key:
                    keys.add(str(key).lower())
        except TypeError:
            pass
    setattr(player, "_skill_key_cache", keys)
    return keys


def _invalidate_skill_caches(player) -> None:
    if not player:
        return
    for attr in (
        "_passive_modifiers_cache",
        "_behavior_tendency_cache",
        "_synergy_profile_cache",
        "_synergy_summary_cache",
    ):
        if hasattr(player, attr):
            setattr(player, attr, None)


def gather_passive_skill_modifiers(player) -> Dict[str, float]:
    """Aggregate additive modifiers from passive skills."""
    if not player:
        return {}
    cache = getattr(player, "_passive_modifiers_cache", None)
    if cache is not None:
        return cache
    modifiers: Dict[str, float] = defaultdict(float)
    for key in list_player_skill_keys(player):
        data = SKILL_DEFINITIONS.get(key)
        if not data:
            continue
        if data.get("type") not in {"passive_buff", "passive_debuff"}:
            continue
        for stat, delta in (data.get("modifiers") or {}).items():
            try:
                modifiers[stat] += float(delta)
            except (TypeError, ValueError):
                continue
    balanced, _summary = _apply_synergy_balancing(player, dict(modifiers))
    memo = dict(balanced)
    setattr(player, "_passive_modifiers_cache", memo)
    return memo


def apply_passive_skill_modifiers(player) -> Dict[str, float]:
    """Apply passive modifiers directly to the player attrs (once per load)."""
    if getattr(player, "_passive_modifiers_applied", False):
        return getattr(player, "_last_passive_modifiers", {})
    modifiers = gather_passive_skill_modifiers(player)
    for stat, delta in modifiers.items():
        try:
            base = getattr(player, stat)
            setattr(player, stat, base + delta)
        except AttributeError:
            continue
        except Exception:
            continue
    setattr(player, "_passive_modifiers_applied", True)
    setattr(player, "_last_passive_modifiers", modifiers)
    return modifiers


ConditionContext = Dict[str, object]
ConditionEvaluator = Callable[[object, ConditionContext], bool]
_CONDITION_EVALUATORS: Dict[str, ConditionEvaluator] = {}


def register_condition(name: str, func: ConditionEvaluator) -> None:
    _CONDITION_EVALUATORS[name] = func


def _evaluate_condition(name: Optional[str], player, context: Optional[ConditionContext]) -> bool:
    if not name:
        return False
    func = _CONDITION_EVALUATORS.get(name)
    if not func:
        return False
    try:
        return func(player, context or {})
    except Exception:
        logger.exception("Condition '%s' failed during evaluation", name)
        return False


def evaluate_situational_skills(
    player,
    context: Optional[ConditionContext] = None,
) -> Tuple[Dict[str, float], List[str]]:
    """Return modifiers and skill keys that activated under the given context."""
    modifiers: Dict[str, float] = defaultdict(float)
    activated: List[str] = []
    if not player:
        return {}, []
    for key in list_player_skill_keys(player):
        data = SKILL_DEFINITIONS.get(key)
        if not data or data.get("type") != "situational":
            continue
        if not _evaluate_condition(data.get("condition"), player, context):
            continue
        for stat, delta in (data.get("modifiers") or {}).items():
            try:
                modifiers[stat] += float(delta)
            except (TypeError, ValueError):
                continue
        activated.append(key)
    balanced, _summary = _apply_synergy_balancing(player, dict(modifiers))
    return balanced, activated


def gather_behavior_tendencies(player) -> Dict[str, float]:
    """Combine AI tendency multipliers advertised by behavior skills."""
    if not player:
        return {}
    cache = getattr(player, "_behavior_tendency_cache", None)
    if cache is not None:
        return cache
    tendencies: Dict[str, float] = {}
    for key in list_player_skill_keys(player):
        data = SKILL_DEFINITIONS.get(key)
        if not data:
            continue
        payload = data.get("ai_tendency")
        if not payload:
            continue
        for tag, multiplier in payload.items():
            try:
                current = tendencies.get(tag, 1.0)
                tendencies[tag] = current * float(multiplier)
            except (TypeError, ValueError):
                continue
    if not tendencies:
        setattr(player, "_behavior_tendency_cache", {})
        return {}
    setattr(player, "_behavior_tendency_cache", tendencies)
    return tendencies


_SYNERGY_RULES: Dict[str, Tuple[float, float]] = {
    "power": (4.0, 0.03),
    "speed": (4.0, 0.03),
    "clutch": (3.0, 0.04),
    "discipline": (4.0, 0.02),
    "defense": (4.0, 0.02),
    "durability": (3.0, 0.03),
    "aggression": (3.0, 0.03),
    "momentum": (3.0, 0.04),
    "utility": (4.0, 0.02),
    "leadership": (3.0, 0.03),
    "resilience": (3.0, 0.03),
    "awareness": (4.0, 0.02),
}


def build_trait_synergy_profile(player) -> Dict[str, float]:
    """Collapse each skill's synergy tags into a single tag-score profile."""
    if not player:
        return {}
    cache = getattr(player, "_synergy_profile_cache", None)
    if cache is not None:
        return cache
    profile: Dict[str, float] = defaultdict(float)
    for key in list_player_skill_keys(player):
        data = SKILL_DEFINITIONS.get(key) or {}
        tags = data.get("synergy_tags") or {}
        for tag, weight in tags.items():
            try:
                profile[tag] += float(weight)
            except (TypeError, ValueError):
                continue
    snapshot = dict(profile)
    setattr(player, "_synergy_profile_cache", snapshot)
    return snapshot


def _calculate_synergy_scalars(profile: Dict[str, float]) -> Dict[str, float]:
    buff_scale = 1.0
    debuff_scale = 1.0
    edge_bonus = 0.0
    for tag, total in profile.items():
        threshold, penalty = _SYNERGY_RULES.get(tag, (5.0, 0.02))
        if total > threshold:
            buff_scale -= (total - threshold) * penalty
        elif total < -threshold:
            relief = (-total - threshold) * penalty * 0.5
            debuff_scale -= relief
        edge_bonus += max(-threshold, min(threshold, total)) * 0.01
    return {
        "buff_scale": max(0.7, buff_scale),
        "debuff_scale": max(0.5, debuff_scale),
        "edge_bonus": edge_bonus,
    }


def _apply_synergy_balancing(player, modifiers: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
    if not modifiers:
        profile = build_trait_synergy_profile(player)
        scalars = _calculate_synergy_scalars(profile)
        summary = dict(scalars)
        summary["profile"] = profile
        if player:
            setattr(player, "_synergy_summary_cache", summary)
        return {}, summary
    profile = build_trait_synergy_profile(player)
    scalars = _calculate_synergy_scalars(profile)
    balanced: Dict[str, float] = {}
    for stat, delta in modifiers.items():
        scale = scalars["buff_scale"] if delta >= 0 else scalars["debuff_scale"]
        balanced[stat] = delta * scale
    summary = dict(scalars)
    summary["profile"] = profile
    if player:
        setattr(player, "_synergy_summary_cache", summary)
    return balanced, summary


def trait_synergy_summary(player) -> Dict[str, float]:
    """Expose the latest synergy profile + scalars for narrative systems."""
    if not player:
        return {"profile": {}, "buff_scale": 1.0, "debuff_scale": 1.0, "edge_bonus": 0.0}
    cache = getattr(player, "_synergy_summary_cache", None)
    if cache is None:
        profile = build_trait_synergy_profile(player)
        scalars = _calculate_synergy_scalars(profile)
        cache = dict(scalars)
        cache["profile"] = profile
        setattr(player, "_synergy_summary_cache", cache)
    return cache


def gather_roll_modifiers(player, context: Optional[ConditionContext] = None) -> Dict[str, float]:
    """Return additive roll modifiers (fatigue/injury odds, etc.) from skills."""
    if not player:
        return {}
    modifiers: Dict[str, float] = defaultdict(float)
    for key in list_player_skill_keys(player):
        data = SKILL_DEFINITIONS.get(key)
        if not data:
            continue
        payload = data.get("roll_modifiers")
        if not payload:
            continue
        if data.get("type") == "situational" and not _evaluate_condition(data.get("condition"), player, context):
            continue
        for roll_key, delta in payload.items():
            try:
                modifiers[roll_key] += float(delta)
            except (TypeError, ValueError):
                continue
    return dict(modifiers)


def _cond_late_inning_pressure(_: object, context: ConditionContext) -> bool:
    inning = int(context.get("inning", 1) or 1)
    threshold = int(context.get("late_inning_threshold", 7) or 7)
    if inning < threshold:
        return False
    margin = context.get("score_margin")
    if margin is None:
        return True
    try:
        margin_val = abs(float(margin))
    except (TypeError, ValueError):
        return True
    pressure = float(context.get("pressure_margin", 2))
    return margin_val <= pressure


def _cond_high_pressure_moment(_: object, context: ConditionContext) -> bool:
    state = str(context.get("pressure_state", "")).lower()
    if state in {"high", "do_or_die", "elimination"}:
        return True
    if context.get("is_elimination_game"):
        return True
    return _cond_late_inning_pressure(None, context)


def _cond_vs_left_handed_pitcher(_: object, context: ConditionContext) -> bool:
    hand = str(context.get("pitcher_hand", "r")).lower()
    return hand.startswith("l")


def _cond_lineup_leadoff(_: object, context: ConditionContext) -> bool:
    slot = context.get("lineup_slot")
    try:
        return int(slot) == 1
    except (TypeError, ValueError):
        return False


def _cond_platoon_advantage(_: object, context: ConditionContext) -> bool:
    batter = str(context.get("batter_hand", "")).lower()[:1]
    pitcher = str(context.get("pitcher_hand", "")).lower()[:1]
    if not batter or not pitcher:
        return False
    if batter == "s":
        return True
    return batter != pitcher


def _cond_two_strike_battle(_: object, context: ConditionContext) -> bool:
    return bool(context.get("is_two_strike"))


def _cond_hot_streak_active(_: object, context: ConditionContext) -> bool:
    if context.get("is_hot_streak"):
        return True
    try:
        return int(context.get("hot_streak_length", 0)) >= 3
    except (TypeError, ValueError):
        return False


def _cond_pinch_hitting_moment(_: object, context: ConditionContext) -> bool:
    return bool(context.get("is_pinch_hitting"))


def _cond_double_play_situation(_: object, context: ConditionContext) -> bool:
    outs = int(context.get("outs", 0) or 0)
    if outs >= 2:
        return False
    runners = context.get("runners_on") or []
    return bool(runners and runners[0])


def _cond_clutch_defense(_: object, context: ConditionContext) -> bool:
    if context.get("pressure_state") == "high":
        return True
    return bool(context.get("is_clutch") or context.get("is_risp"))


def _cond_big_game_stage(_: object, context: ConditionContext) -> bool:
    if context.get("is_postseason") or context.get("is_elimination_game"):
        return True
    importance = str(context.get("game_importance", "regular")).lower()
    return importance in {"koshien", "tournament", "championship", "final"}


def _cond_bullpen_fireman(_: object, context: ConditionContext) -> bool:
    if not context.get("is_relief_pitcher"):
        return False
    if context.get("inherited_runners"):
        return True
    runners = context.get("runners_on") or []
    return bool(runners and any(runners))


def _cond_closer_ninth(_: object, context: ConditionContext) -> bool:
    inning = int(context.get("inning", 1) or 1)
    role = str(context.get("pitcher_role", "")).upper()
    return inning >= 9 and (role == "CLOSER" or context.get("is_relief_pitcher"))


def _cond_team_trailing(_: object, context: ConditionContext) -> bool:
    return bool(context.get("is_trailing"))


def _cond_scouting_edge(_: object, context: ConditionContext) -> bool:
    return bool(context.get("has_scouting_edge"))


def _cond_clutch_superstate(_: object, context: ConditionContext) -> bool:
    return bool(
        context.get("is_clutch")
        or context.get("is_risp")
        or context.get("pressure_state") == "high"
    )


def _cond_shutdown_mode(_: object, context: ConditionContext) -> bool:
    if context.get("pressure_state") == "high":
        return True
    try:
        return abs(float(context.get("score_diff", 0))) <= 1
    except (TypeError, ValueError):
        return False


def _cond_low_pressure_window(_: object, context: ConditionContext) -> bool:
    return context.get("pressure_state") == "normal" and not context.get("is_risp")


def _cond_hostile_environment(_: object, context: ConditionContext) -> bool:
    if context.get("is_hostile_env"):
        return True
    return bool(not context.get("is_home_game") and context.get("crowd_factor", 0) < 0)


def _cond_routine_online(_: object, context: ConditionContext) -> bool:
    return bool(context.get("routine_active"))


def _cond_postseason_stage(_: object, context: ConditionContext) -> bool:
    return bool(context.get("is_postseason"))


def _cond_season_opener_lag(_: object, context: ConditionContext) -> bool:
    return bool(context.get("is_season_opener"))


def _cond_slump_active(_: object, context: ConditionContext) -> bool:
    return bool(context.get("is_slumping"))


def _cond_cleanup_spot(_: object, context: ConditionContext) -> bool:
    try:
        return int(context.get("lineup_slot")) == 4
    except (TypeError, ValueError):
        return False


def _cond_cleanup_risp(_: object, context: ConditionContext) -> bool:
    return _cond_cleanup_spot(None, context) and bool(context.get("is_risp"))


def _cond_ace_start(player, context: ConditionContext) -> bool:
    if context.get("is_ace_start"):
        return True
    role = str(context.get("pitcher_role", "") or getattr(player, "role", "")).upper()
    return role == "ACE"


def _cond_runners_in_scoring_pos(_: object, context: ConditionContext) -> bool:
    return bool(context.get("is_risp"))


def _cond_closer_role(player, context: ConditionContext) -> bool:
    role = str(context.get("pitcher_role", "") or getattr(player, "role", "")).upper()
    return role == "CLOSER"


def _cond_spot_start(player, context: ConditionContext) -> bool:
    if context.get("is_spot_start"):
        return True
    return bool(getattr(player, "spot_start", False))


def _position_matches(value: Optional[str], *targets: str) -> bool:
    label = str(value or "").upper()
    return any(label == target or label in target for target in targets)


def _cond_dh_assignment(player, context: ConditionContext) -> bool:
    position = context.get("player_position") or getattr(player, "position", None)
    return _position_matches(position, "DH", "DESIGNATED HITTER")


def _cond_catcher_assignment(player, context: ConditionContext) -> bool:
    position = context.get("player_position") or getattr(player, "position", None)
    return _position_matches(position, "C", "CATCHER")


def _cond_first_base_assignment(player, context: ConditionContext) -> bool:
    position = context.get("player_position") or getattr(player, "position", None)
    return _position_matches(position, "1B", "FIRST BASE")


def _cond_second_base_assignment(player, context: ConditionContext) -> bool:
    position = context.get("player_position") or getattr(player, "position", None)
    return _position_matches(position, "2B", "SECOND BASE")


def _cond_shortstop_assignment(player, context: ConditionContext) -> bool:
    position = context.get("player_position") or getattr(player, "position", None)
    return _position_matches(position, "SS", "SHORTSTOP")


def _cond_third_base_assignment(player, context: ConditionContext) -> bool:
    position = context.get("player_position") or getattr(player, "position", None)
    return _position_matches(position, "3B", "THIRD BASE")


def _cond_outfield_assignment(player, context: ConditionContext) -> bool:
    position = str(context.get("player_position") or getattr(player, "position", "")).upper()
    return position in {"LF", "CF", "RF", "OF", "OUTFIELD"}


def _cond_game_heat_up(_: object, context: ConditionContext) -> bool:
    if context.get("inning", 1) >= 4:
        return True
    try:
        return int(context.get("pitch_count", 0)) >= 45
    except (TypeError, ValueError):
        return False


register_condition("late_inning_pressure", _cond_late_inning_pressure)
register_condition("high_pressure_moment", _cond_high_pressure_moment)
register_condition("vs_left_handed_pitcher", _cond_vs_left_handed_pitcher)
register_condition("lineup_leadoff", _cond_lineup_leadoff)
register_condition("platoon_advantage", _cond_platoon_advantage)
register_condition("two_strike_battle", _cond_two_strike_battle)
register_condition("hot_streak_active", _cond_hot_streak_active)
register_condition("pinch_hitting_moment", _cond_pinch_hitting_moment)
register_condition("double_play_situation", _cond_double_play_situation)
register_condition("clutch_defense", _cond_clutch_defense)
register_condition("big_game_stage", _cond_big_game_stage)
register_condition("bullpen_fireman", _cond_bullpen_fireman)
register_condition("closer_ninth", _cond_closer_ninth)
register_condition("team_trailing", _cond_team_trailing)
register_condition("scouting_edge", _cond_scouting_edge)
register_condition("clutch_superstate", _cond_clutch_superstate)
register_condition("shutdown_mode", _cond_shutdown_mode)
register_condition("low_pressure_window", _cond_low_pressure_window)
register_condition("hostile_environment", _cond_hostile_environment)
register_condition("routine_online", _cond_routine_online)
register_condition("postseason_stage", _cond_postseason_stage)
register_condition("season_opener_lag", _cond_season_opener_lag)
register_condition("slump_active", _cond_slump_active)
register_condition("cleanup_spot", _cond_cleanup_spot)
register_condition("cleanup_risp", _cond_cleanup_risp)
register_condition("ace_start", _cond_ace_start)
register_condition("runners_in_scoring_pos", _cond_runners_in_scoring_pos)
register_condition("closer_role", _cond_closer_role)
register_condition("spot_start", _cond_spot_start)
register_condition("dh_assignment", _cond_dh_assignment)
register_condition("catcher_assignment", _cond_catcher_assignment)
register_condition("first_base_assignment", _cond_first_base_assignment)
register_condition("second_base_assignment", _cond_second_base_assignment)
register_condition("shortstop_assignment", _cond_shortstop_assignment)
register_condition("third_base_assignment", _cond_third_base_assignment)
register_condition("outfield_assignment", _cond_outfield_assignment)
register_condition("game_heat_up", _cond_game_heat_up)


def player_has_skill(player, skill_key: str) -> bool:
    if not player or not skill_key:
        return False
    return skill_key.lower() in _skill_key_cache(player)


def list_player_skill_keys(player) -> List[str]:
    """Return sorted skill keys currently tracked for the player."""
    return sorted(_skill_key_cache(player))


def list_meetable_skills(player) -> List[str]:
    """Return skills where the player currently satisfies all stat gates."""
    if not player:
        return []
    owned = _skill_key_cache(player)
    eligible: List[str] = []
    for key, data in SKILL_DEFINITIONS.items():
        if key.lower() in owned:
            continue
        if _meets_all_requirements(player, data.get("requirements", [])):
            eligible.append(key)
    return eligible


def grant_skill_by_key(
    session,
    player,
    skill_key: str,
    *,
    owned_cache: Optional[Set[str]] = None,
) -> Optional[str]:
    """Grant the provided skill to the player, bypassing requirement checks."""
    if not player or not player.id or not skill_key:
        return None

    cache = owned_cache if owned_cache is not None else _skill_key_cache(player)
    setattr(player, "_skill_key_cache", cache)
    canonical = str(skill_key).lower()
    if canonical in cache:
        return None

    data = SKILL_DEFINITIONS.get(canonical)
    db_key = canonical if data else str(skill_key)
    display_name = (data or {}).get("name", skill_key)

    new_skill = PlayerSkill(
        player_id=player.id,
        skill_key=db_key,
        acquired_date=datetime.now(timezone.utc),
        is_active=True,
    )
    session.add(new_skill)
    if hasattr(player, "skills"):
        player.skills.append(new_skill)
    cache.add(db_key.lower())
    _invalidate_skill_caches(player)
    session.flush()
    return display_name


def remove_skill_by_key(session, player, skill_key: str) -> bool:
    """Remove a skill from the player and clear relevant caches."""
    if not session or not player or not player.id or not skill_key:
        return False

    canonical = str(skill_key).lower()
    cache = _skill_key_cache(player)
    target_entries = []

    # Prefer the relationship list when available to keep ORM state in sync.
    skill_rel = getattr(player, "skills", None)
    if skill_rel:
        for entry in list(skill_rel):
            key = getattr(entry, "skill_key", None)
            if key and str(key).lower() == canonical:
                target_entries.append(entry)

    # Fall back to querying when cache/relationship is out of date.
    if not target_entries:
        db_entries = (
            session.query(PlayerSkill)
            .filter(PlayerSkill.player_id == player.id)
            .all()
        )
        target_entries = [entry for entry in db_entries if str(getattr(entry, "skill_key", "")).lower() == canonical]

    if not target_entries:
        return False

    removed = False
    for entry in target_entries:
        try:
            session.delete(entry)
        except Exception:
            continue
        if skill_rel and entry in skill_rel:
            skill_rel.remove(entry)
        removed = True

    if not removed:
        return False

    cache.discard(canonical)
    _invalidate_skill_caches(player)

    session.flush()
    return True


def sync_player_skills(
    session,
    *,
    prune_unknown: bool = True,
    fix_duplicates: bool = True,
    dry_run: bool = False,
    loaded_only: bool | None = None,
):
    """Clean up PlayerSkill rows so they align with the active catalog."""
    if not session:
        return {
            "players_scanned": 0,
            "unknown_entries_pruned": 0,
            "duplicate_entries_pruned": 0,
            "dry_run": True,
        }

    valid_keys = {key.lower() for key in SKILL_DEFINITIONS.keys()}
    stats = {
        "players_scanned": 0,
        "unknown_entries_pruned": 0,
        "duplicate_entries_pruned": 0,
        "dry_run": dry_run,
    }

    if loaded_only is None:
        loaded_only = bool(os.getenv("PYTEST_CURRENT_TEST"))

    query = session.query(Player)
    try:
        query = query.options(selectinload(Player.skills))
    except Exception:
        # Older SQLAlchemy versions without selectinload fall back to lazy loading.
        pass

    players = list(session.identity_map.values()) if loaded_only else query.all()
    for player in players:
        stats["players_scanned"] += 1
        skill_rel = getattr(player, "skills", []) or []
        skills = list(skill_rel)
        if not skills:
            continue

        entry_map: Dict[str, List[PlayerSkill]] = defaultdict(list)
        for entry in skills:
            canonical = str(getattr(entry, "skill_key", "")).lower()
            entry_map[canonical].append(entry)

        cache = _skill_key_cache(player)
        modified = False

        for canonical, entries in entry_map.items():
            if not canonical:
                continue

            if canonical not in valid_keys:
                stats["unknown_entries_pruned"] += len(entries)
                if prune_unknown and not dry_run:
                    for entry in entries:
                        session.delete(entry)
                        if entry in skill_rel:
                            skill_rel.remove(entry)
                    cache.discard(canonical)
                    modified = True
                continue

            if fix_duplicates and len(entries) > 1:
                stats["duplicate_entries_pruned"] += len(entries) - 1
                if dry_run:
                    continue
                keep_entry = entries[0]
                for entry in entries[1:]:
                    session.delete(entry)
                    if entry in skill_rel:
                        skill_rel.remove(entry)
                if keep_entry not in skill_rel:
                    skill_rel.append(keep_entry)
                modified = True

        if modified and not dry_run:
            _invalidate_skill_caches(player)

    if not dry_run:
        session.flush()

    return stats


def _describe_requirement_failure(player, requirements: Sequence[Dict]) -> str:
    for requirement in requirements:
        if _meets_single_requirement(player, requirement):
            continue
        stat = requirement.get("stat", "unknown")
        value = getattr(player, stat, None)
        pieces = []
        if "min" in requirement:
            pieces.append(f"min={requirement['min']}")
        if "max" in requirement:
            pieces.append(f"max={requirement['max']}")
        if "equals" in requirement:
            pieces.append(f"equals={requirement['equals']}")
        if "equals_any" in requirement:
            pieces.append(f"equals_any={requirement['equals_any']}")
        requirement_desc = ", ".join(pieces) or "unspecified bounds"
        return f"{stat} requirement ({requirement_desc}) actual={value}"
    return "undetermined requirement failure"
