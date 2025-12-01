"""Skill definitions and acquisition helpers."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import logging
import os
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from database.setup_db import PlayerSkill
from game.rng import get_rng

logger = logging.getLogger(__name__)
PROGRESSION_DEBUG = os.getenv("PROGRESSION_DEBUG", "").lower() in {"1", "true", "yes"}
_SKILL_RNG = get_rng()

# ---------------------------------------------------------------------------
# Skill catalog
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Acquisition helpers
# ---------------------------------------------------------------------------
def check_and_grant_skills(
    session,
    player,
    *,
    probability_hook: Optional[Callable[[object, str, Dict], float]] = None,
    rng=None,
) -> List[str]:
    """Grant any newly-qualified skills for the provided player.

    Returns a list of human-readable skill names that were unlocked during the check.
    """
    if not player or not player.id:
        return []

    cache = _skill_key_cache(player)
    owned_keys = set(cache)
    unlocked: List[str] = []

    random_source = rng or _SKILL_RNG

    for key, data in SKILL_DEFINITIONS.items():
        key_lower = key.lower()
        if key_lower in owned_keys:
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

        display_name = grant_skill_by_key(session, player, key)
        if display_name:
            owned_keys.add(key_lower)
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
    memo = dict(modifiers)
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
    return dict(modifiers), activated


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


register_condition("late_inning_pressure", _cond_late_inning_pressure)
register_condition("high_pressure_moment", _cond_high_pressure_moment)
register_condition("vs_left_handed_pitcher", _cond_vs_left_handed_pitcher)
register_condition("lineup_leadoff", _cond_lineup_leadoff)


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


def grant_skill_by_key(session, player, skill_key: str) -> Optional[str]:
    """Grant the provided skill to the player, bypassing requirement checks."""
    if not player or not player.id or not skill_key:
        return None

    cache = _skill_key_cache(player)
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
    session.flush()
    return display_name


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
