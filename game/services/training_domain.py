from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from core.config_loader import ConfigLoader
from core.utils import clamp
from game.services.dtos import PlayerTrainingDTO, PitchRepertoireDTO, PlayerXPEntryDTO
from game.services.progression_port import ProgressionPort


FATIGUE_COSTS = ConfigLoader.get_section("fatigue_costs", {}) or {}
XP_GAINS = ConfigLoader.get_section("xp_gains", {}) or {}
TRAINING_EFFICIENCY = ConfigLoader.get_section("training_efficiency", {}) or {}
INJURY_RISK = ConfigLoader.get_section("injury_risk", {}) or {}

XP_TRACKED_STATS = {
    "control",
    "velocity",
    "stamina",
    "movement",
    "power",
    "contact",
    "speed",
    "fielding",
    "throwing",
    "command",
}

BREAKTHROUGH_BASE_CHANCE = 0.01
BREAKTHROUGH_SCALE = 0.0004
BREAKTHROUGH_MIN = 0.005
BREAKTHROUGH_MAX = 0.08


@dataclass
class TrainingResult:
    dto: PlayerTrainingDTO
    summary: str
    fatigue_change: int
    stat_changes: Dict[str, float]
    xp_gains: Dict[str, float]
    mastery_gains: Dict[str, int]
    breakthrough: Optional[dict]
    skills_unlocked: List[str]
    milestones: List


def _xp_threshold(stat_value: Optional[float]) -> float:
    value = stat_value or 0.0
    return max(3.0, 3.0 + (value / 20.0))


def _apply_training_xp(dto: PlayerTrainingDTO, xp_gains: Dict[str, float]) -> Tuple[Dict[str, int], Dict[str, float]]:
    pool = {entry.stat_key: float(entry.xp or 0.0) for entry in dto.xp_entries}
    level_ups: Dict[str, int] = {}

    for stat, gain in xp_gains.items():
        current_value = dto.stats.get(stat, 0)
        total_xp = pool.get(stat, 0.0) + gain
        threshold = _xp_threshold(current_value)
        applied_levels = 0
        while total_xp >= threshold:
            total_xp -= threshold
            current_value += 1
            applied_levels += 1
            threshold = _xp_threshold(current_value)
        pool[stat] = total_xp
        if applied_levels:
            dto.stats[stat] = current_value
            level_ups[stat] = applied_levels

    dto.xp_entries = [PlayerXPEntryDTO(stat_key=k, xp=v) for k, v in pool.items() if v > 0]
    return level_ups, pool


def _maybe_trigger_breakthrough(dto: PlayerTrainingDTO, xp_gains: dict, rng: random.Random) -> Optional[dict]:
    if not xp_gains:
        return None
    determination = dto.attributes.get("determination")
    if determination is None:
        determination = dto.attributes.get("drive", 50) or 50
    chance = BREAKTHROUGH_BASE_CHANCE + max(0.0, determination - 50) * BREAKTHROUGH_SCALE
    chance = max(BREAKTHROUGH_MIN, min(BREAKTHROUGH_MAX, chance))
    roll = rng.random()
    if roll > chance:
        return None
    focus_stat = max(xp_gains.items(), key=lambda item: item[1])[0]
    current_value = (dto.stats.get(focus_stat, 0) or 0) + 1
    dto.stats[focus_stat] = current_value
    return {
        "stat": focus_stat,
        "new_value": current_value,
        "chance": chance,
        "roll": roll,
    }


def _update_pitch_mastery(dto: PlayerTrainingDTO, rng: random.Random) -> Tuple[str, Dict[str, int]]:
    repertoire = dto.pitch_repertoire or []
    if not repertoire:
        return "No pitches recorded yet. Learn a pitch first.", {}
    target = sorted(
        repertoire,
        key=lambda p: ((p.mastery_level or 0), (p.mastery_xp or 0)),
    )[0]
    current_xp = int(target.mastery_xp or 0)
    # Simple mastery progression without external tables
    base_pct = rng.uniform(0.05, 0.10)
    inspiration = rng.random() < 0.15
    if inspiration:
        base_pct = rng.uniform(0.15, 0.20)
    # Approximate mastery thresholds: grow span with level for slower progress later
    span = max(25, current_xp + 50)
    gain = max(1, int(round(span * base_pct)))
    target.mastery_xp = current_xp + gain
    mastery_gains = {target.pitch_name: gain}
    summary = f"Bullpen Session: {target.pitch_name} +{gain} XP"
    if inspiration:
        summary += " (inspiration)"
    return summary, mastery_gains


def apply_training_action_dto(
    player: PlayerTrainingDTO,
    action_type: str,
    *,
    rng: Optional[random.Random] = None,
    progression_service: Optional[ProgressionPort] = None,
    progression_state: Optional[dict] = None,
) -> TrainingResult:
    rng = rng or random.Random()

    fatigue = player.fatigue or 0
    style = player.growth_tag or player.attributes.get("growth_tag") or "Normal"
    conditioning = player.conditioning if player.conditioning is not None else 50
    injury_days = player.injury_days or 0
    jersey_num = player.jersey_number
    position = player.position

    costs = FATIGUE_COSTS
    xp_rates = XP_GAINS
    eff = TRAINING_EFFICIENCY
    risk = INJURY_RISK

    def _is_reserve_player(p: PlayerTrainingDTO) -> bool:
        role = (p.attributes.get("role", "") or "").upper()
        jersey = p.jersey_number
        if role == "RESERVE":
            return True
        return jersey is not None and jersey >= 90

    if injury_days > 0:
        return TrainingResult(
            dto=player,
            summary=f"Injured ({injury_days} days left). Cannot train.",
            fatigue_change=0,
            stat_changes={},
            xp_gains={},
            mastery_gains={},
            breakthrough=None,
            skills_unlocked=[],
            milestones=[],
        )

    summary = ""
    fatigue_change = 0
    stat_gains: Dict[str, float] = {}
    mastery_gains: Dict[str, int] = {}

    if action_type == "rest":
        base_rest = costs.get("rest", -15)
        fatigue_change = int(base_rest)
        summary = f"Rest Day: Recovered {abs(fatigue_change)} fatigue."
    elif action_type == "team_practice":
        fatigue_change = costs.get("team_practice", 15)
        base_gain = xp_rates.get("team_practice_base", 0.2)
        stat_gains = {"control": base_gain, "power": base_gain, "contact": base_gain, "stamina": base_gain}
        summary = "Team Practice: General drills."
    elif action_type == "practice_match":
        fatigue_change = costs.get("practice_match", 35)
        base_gain = xp_rates.get("match_a_team_base", 0.5)
        stat_gains = {"control": base_gain, "velocity": base_gain / 5, "power": base_gain, "contact": base_gain}
        summary = "A-Team Practice Match: Intense competition!"
    elif action_type == "b_team_match":
        if not _is_reserve_player(player):
            return TrainingResult(
                dto=player,
                summary="Bench players cannot join B-Team scrimmages; coach keeps them out.",
                fatigue_change=0,
                stat_changes={},
                xp_gains={},
                mastery_gains={},
                breakthrough=None,
                skills_unlocked=[],
                milestones=[],
            )
        is_starter = jersey_num is not None and jersey_num <= 9
        base_b_cost = costs.get("b_team_match", 25)
        if is_starter:
            fatigue_change = int(round(base_b_cost * 0.8))
            base_gain = xp_rates.get("match_b_team_starter", 0.2)
            stat_gains = {"control": base_gain, "stamina": base_gain}
            summary = "Played in B-Game. Too easy for a starter (Low gains)."
        else:
            fatigue_change = int(round(base_b_cost * 1.2))
            base_gain = xp_rates.get("match_b_team_reserve", 0.7)
            stat_gains = {"control": base_gain, "power": base_gain, "contact": base_gain, "fielding": base_gain}
            if position == "Pitcher":
                stat_gains["velocity"] = base_gain * 0.5
                stat_gains["stamina"] = base_gain
            summary = "B-Team Match: You fought hard to prove yourself! (High XP)"
    elif action_type == "study":
        fatigue_change = costs.get("study", 5)
        stat_gains = {"academic_skill": xp_rates.get("study", 0.3), "test_score": xp_rates.get("study_test", 0.2)}
        summary = "Study session complete."
    elif action_type == "social":
        fatigue_change = costs.get("social", 5)
        summary = "Social Activity: Reduced mental stress."
    elif action_type == "mind":
        fatigue_change = costs.get("mind", 0)
        base_gain = xp_rates.get("mind_training_base", 0.1)
        stat_gains = {"control": base_gain, "contact": base_gain}
        summary = "Mind & Focus: Visualisation training."
    elif action_type == "bullpen_session":
        fatigue_change = costs.get("bullpen_session", 18)
        summary, mastery_gains = _update_pitch_mastery(player, rng, fatigue_change)
    elif action_type and action_type.startswith("train_"):
        efficiency = 1.0
        if fatigue > eff.get("threshold_exhausted", 80):
            efficiency = eff.get("multiplier_exhausted", 0.3)
        elif fatigue > eff.get("threshold_tired", 50):
            efficiency = eff.get("multiplier_tired", 0.7)

        synergy = 1.0
        drill = action_type.replace("train_", "")

        if drill == "control":
            stat_gains = {"control": 1.0}
            if style == "Technical":
                synergy = 1.5
        elif drill == "velocity":
            stat_gains = {"velocity": 0.3}
            if style in {"Power", "Pitcher"}:
                synergy = 1.5
        elif drill == "stamina":
            stat_gains = {"stamina": 1.0}
            if style == "Balanced":
                synergy = 1.2
        elif drill == "power":
            stat_gains = {"power": 1.0}
            if style == "Power":
                synergy = 1.5
        elif drill == "contact":
            stat_gains = {"contact": 1.0}
            if style == "Technical":
                synergy = 1.5
        elif drill == "speed":
            stat_gains = {"speed": 1.0}
            if style == "Speed":
                synergy = 1.5

        for k in stat_gains:
            stat_gains[k] *= efficiency * synergy

        fatigue_change = costs.get("drill_generic", 10)
        gain_mult = 1.0
        cond_note = ""
        if gain_mult > 1.0:
            cond_note = " (Great Form!)"
        elif gain_mult < 1.0:
            cond_note = " (Sluggish...)"
        summary = f"Drill ({drill.title()}): Session complete.{cond_note}"

    slump_timer = player.slump_timer or 0
    if slump_timer > 0:
        if action_type == "rest":
            stat_gains = {k: v * 0.8 for k, v in stat_gains.items()}
            fatigue_change -= 3
        else:
            stat_gains = {k: v * 0.6 for k, v in stat_gains.items()}
            summary += " Confidence slump slows your rhythm."

    fatigue = max(0, min(100, fatigue + fatigue_change))
    player.fatigue = fatigue

    xp_gains: Dict[str, float] = {}
    applied_stat_changes: Dict[str, float] = {}

    for stat, value in stat_gains.items():
        variance = rng.uniform(0.9, 1.1)
        final_value = value * variance
        if stat in XP_TRACKED_STATS:
            xp_gains[stat] = xp_gains.get(stat, 0.0) + final_value
        else:
            current = player.stats.get(stat, 0) or 0
            player.stats[stat] = current + final_value
            applied_stat_changes[stat] = applied_stat_changes.get(stat, 0) + final_value

    if "academic_skill" in stat_gains:
        player.stats["academic_skill"] = int(round(clamp(player.stats.get("academic_skill", 0), 25, 110)))
    if "test_score" in stat_gains:
        player.stats["test_score"] = int(round(clamp(player.stats.get("test_score", 0), 0, 100)))

    level_ups: Dict[str, int] = {}
    breakthrough_event: Optional[dict] = None
    if xp_gains:
        level_ups, _ = _apply_training_xp(player, xp_gains)
        breakthrough_event = _maybe_trigger_breakthrough(player, xp_gains, rng)

    for stat, amount in level_ups.items():
        applied_stat_changes[stat] = applied_stat_changes.get(stat, 0) + amount

    unlocked_skills: List[str] = []
    milestone_unlocks: List = []
    if progression_service and player.id:
        cache = progression_state or {}
        owned_keys = cache.get("skill_keys")
        if owned_keys is None:
            owned_keys = set()
            cache["skill_keys"] = owned_keys
        definitions = cache.get("milestone_defs")
        stats_cache = cache.get("milestone_stats")
        unlocked_skills = progression_service.grant_skills(player.id, owned_keys=owned_keys)
        milestone_unlocks = progression_service.process_milestones(
            player.id,
            definitions_cache=definitions,
            stats_cache=stats_cache,
            owned_keys=owned_keys,
        )
        cache["milestone_defs"] = definitions or cache.get("milestone_defs")
        cache["milestone_stats"] = stats_cache or cache.get("milestone_stats", {})
        if slump_timer > 0:
            progression_service.adjust_morale(player.id, 4)

    return TrainingResult(
        dto=player,
        summary=summary,
        fatigue_change=fatigue_change,
        stat_changes=applied_stat_changes,
        xp_gains=xp_gains,
        mastery_gains=mastery_gains,
        breakthrough=breakthrough_event,
        skills_unlocked=unlocked_skills,
        milestones=milestone_unlocks,
    )
