"""Catcher intelligence helpers that call pitches based on threat and memory."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple

from game.rng import get_rng
from game.pitch_types import PitchDefinition, get_pitch_definition
from match_engine.pitch_logic import describe_batter_tells, get_arsenal, get_last_pitch_call
from match_engine.pitch_definitions import PITCH_TYPES

_rng = get_rng()
_PITCH_CACHE: Dict[str, PitchDefinition] = {}


@dataclass
class PitchMemory:
    """Aggregated outcomes for a single pitch against a specific batter."""

    attempts: int = 0
    wins: int = 0
    hard_contact: int = 0
    chase_swings: int = 0
    last_location: str = "Zone"

    def success_rate(self) -> float:
        if self.attempts <= 0:
            return 0.5
        return self.wins / self.attempts

    def pressure(self) -> float:
        if self.attempts <= 0:
            return 0.0
        return (self.hard_contact / self.attempts) * 0.5


@dataclass
class CatcherMemory:
    """Per-game notebook shared between catcher and pitcher."""

    vs_batter: Dict[int, Dict[str, PitchMemory]] = field(default_factory=dict)

    def snapshot(self, batter_id: Optional[int]) -> Dict[str, PitchMemory]:
        if batter_id is None:
            return {}
        return self.vs_batter.setdefault(batter_id, {})

    def record(self, batter_id: Optional[int], pitch_name: str, *, outcome: str, location: str = "Zone") -> None:
        if batter_id is None or not pitch_name:
            return
        batter_memory = self.snapshot(batter_id)
        entry = batter_memory.setdefault(pitch_name, PitchMemory())
        entry.attempts += 1
        entry.last_location = location or entry.last_location
        if outcome in {"whiff", "weak_contact", "strike"}:
            entry.wins += 1
        if outcome == "hard_contact":
            entry.hard_contact += 1
        if outcome == "chase":
            entry.chase_swings += 1


@dataclass
class PitchCall:
    pitch: object
    location: str
    intent: str
    confidence: float
    reason: str = ""


def get_or_create_catcher_memory(state) -> CatcherMemory:
    memory = getattr(state, "catcher_memory", None)
    if not isinstance(memory, CatcherMemory):
        memory = CatcherMemory()
        setattr(state, "catcher_memory", memory)
    return memory


def generate_catcher_sign(
    catcher,
    pitcher,
    batter,
    state,
    *,
    memory: Optional[CatcherMemory] = None,
    exclude_pitch_name: Optional[str] = None,
) -> PitchCall:
    """Select a pitch + location by combining threat scouting and memory."""

    raw_arsenal = get_arsenal(getattr(pitcher, "id", None)) or []
    arsenal = [p for p in raw_arsenal if not exclude_pitch_name or p.pitch_name != exclude_pitch_name]
    if not arsenal:
        arsenal = list(raw_arsenal)
    if not arsenal:
        raise ValueError("Pitcher has no arsenal available for catcher AI.")

    memory = memory or get_or_create_catcher_memory(state)
    batter_id = getattr(batter, "id", None)
    batter_stats = _infer_batter_profile(batter)
    pitcher_state = _assess_pitcher_state(pitcher, state)
    batter_memory = memory.snapshot(batter_id)
    last_call = get_last_pitch_call(state, getattr(pitcher, "id", None), batter_id)

    best_pitch = arsenal[0]
    best_score = float("-inf")
    best_reason = ""

    for pitch in arsenal:
        score, reason = _score_pitch(
            pitch,
            batter_stats,
            pitcher_state,
            batter_memory.get(pitch.pitch_name),
            last_call,
            describe_batter_tells(state, batter),
        )
        if score > best_score:
            best_score = score
            best_pitch = pitch
            best_reason = reason

    location = _choose_location(state, batter_stats, batter_memory.get(best_pitch.pitch_name))
    intent = _choose_intent(best_pitch, pitcher_state)
    confidence = _compute_confidence(best_score, pitcher_state)

    return PitchCall(
        pitch=best_pitch,
        location=location,
        intent=intent,
        confidence=confidence,
        reason=best_reason,
    )


def _infer_batter_profile(batter) -> Dict[str, float]:
    contact = getattr(batter, "contact", 50) or 50
    power = getattr(batter, "power", 50) or 50
    discipline = getattr(batter, "discipline", 50) or 50
    aggression = getattr(batter, "aggression", 50) or getattr(batter, "drive", 50) or 50
    clutch = getattr(batter, "clutch", 50) or 50
    return {
        "contact": contact,
        "power": power,
        "discipline": discipline,
        "aggression": aggression,
        "clutch": clutch,
        "hot_zone": "zone" if contact >= 65 else "all",  # crude but purposeful
        "chase_prone": discipline <= 45,
        "pull_power": power >= 70 and aggression >= 60,
    }


def _assess_pitcher_state(pitcher, state) -> Dict[str, float]:
    pitch_counts = getattr(state, "pitch_counts", {}) or {}
    pitcher_id = getattr(pitcher, "id", None)
    total_pitches = pitch_counts.get(pitcher_id, 0)
    stamina = getattr(pitcher, "stamina", 60) or 60
    confidence = 0
    conf_map = getattr(state, "confidence_map", {}) or {}
    if pitcher_id is not None:
        confidence = conf_map.get(pitcher_id, 0)
    fatigue_penalty = max(0.0, (total_pitches - stamina)) * 0.25
    return {
        "stamina": stamina,
        "confidence": confidence,
        "fatigue": fatigue_penalty,
        "count": (state.balls, state.strikes),
    }


def _family(pitch_name: str) -> str:
    definition = PITCH_TYPES.get(pitch_name, {})
    return (definition.get("family") or "Fastball").title()


def _score_pitch(
    pitch,
    batter_stats: Dict[str, float],
    pitcher_state: Dict[str, float],
    memory_entry: Optional[PitchMemory],
    last_call: Optional[Dict[str, object]],
    batter_tells: Iterable[str],
) -> Tuple[float, str]:
    score = pitch.quality
    reason_bits = [pitch.pitch_name]
    family = _family(pitch.pitch_name)

    fatigue_penalty, fatigue_reason = _fatigue_guard(pitch.pitch_name, pitcher_state["fatigue"])
    if fatigue_penalty:
        score -= fatigue_penalty
        reason_bits.append(fatigue_reason)
    if batter_stats["pull_power"] and family in {"Fastball", "Cutter"}:
        score -= 3
        reason_bits.append("(batter hunts heat)")
    if batter_stats["chase_prone"] and family != "Fastball":
        score += 2
        reason_bits.append("(will chase spin)")

    if memory_entry:
        sr = memory_entry.success_rate()
        score += (sr - 0.5) * 10
        if memory_entry.hard_contact:
            score -= memory_entry.hard_contact * 1.5
        reason_bits.append(f"(vs batter SR {sr:.2f})")

    last_pitch_name = last_call.get("pitch_name") if last_call else None
    if last_pitch_name and last_pitch_name == pitch.pitch_name:
        score -= 2.5
    if last_call and last_call.get("family") == family:
        score -= 1.0

    synergy_bonus, synergy_tag = _calculate_synergy(last_pitch_name, pitch.pitch_name)
    if synergy_bonus:
        score += synergy_bonus
        reason_bits.append(synergy_tag)

    if batter_tells:
        matched = sum(1 for clue in batter_tells if family.lower() in clue.lower())
        score -= matched * 1.5

    score += _rng.uniform(-1.0, 1.0)  # slight unpredictability
    return score, " ".join(reason_bits)


def _choose_location(state, batter_stats, memory_entry: Optional[PitchMemory]) -> str:
    balls = getattr(state, "balls", 0)
    strikes = getattr(state, "strikes", 0)
    location = "Zone"
    if strikes >= 2 and (batter_stats["chase_prone"] or (memory_entry and memory_entry.success_rate() >= 0.6)):
        location = "Chase"
    elif balls - strikes >= 2:
        location = "Zone"
    elif memory_entry and memory_entry.last_location == "Chase" and memory_entry.success_rate() >= 0.55:
        location = "Chase"
    elif batter_stats["hot_zone"] != "zone" and strikes >= 1:
        location = "Chase"
    return location


def _choose_intent(pitch, pitcher_state) -> str:
    family = _family(pitch.pitch_name)
    if family in {"Fastball", "Sinker"} and pitcher_state["confidence"] >= 10:
        return "Challenge"
    if family in {"Changeup", "Splitter"} and pitcher_state["stamina"] <= 45:
        return "Deception"
    return "Normal"


def _compute_confidence(score: float, pitcher_state: Dict[str, float]) -> float:
    base = 0.55 + (pitcher_state["confidence"] / 200.0) - (pitcher_state["fatigue"] / 40.0)
    adjusted = base + (score / 100.0)
    return max(0.2, min(0.95, adjusted))


__all__ = [
    "CatcherMemory",
    "PitchCall",
    "generate_catcher_sign",
    "get_or_create_catcher_memory",
]


def _pitch_profile(pitch_name: Optional[str]) -> Optional[PitchDefinition]:
    if not pitch_name:
        return None
    cache_key = pitch_name.lower()
    if cache_key in _PITCH_CACHE:
        return _PITCH_CACHE[cache_key]
    try:
        definition = get_pitch_definition(pitch_name)
    except KeyError:
        return None
    _PITCH_CACHE[cache_key] = definition
    return definition


def _fatigue_guard(pitch_name: str, fatigue_score: float) -> Tuple[float, str]:
    definition = _pitch_profile(pitch_name)
    if not definition or fatigue_score <= 2:
        return 0.0, ""
    penalty = 0.0
    if definition.stamina_cost >= 6:
        penalty = max(0.0, (fatigue_score - 3) * 0.6)
    elif definition.stamina_cost >= 5:
        penalty = max(0.0, (fatigue_score - 5) * 0.4)
    if not penalty:
        return 0.0, ""
    capped = min(4.0, penalty)
    return capped, f"(arm saver -{capped:.1f})"


def _calculate_synergy(prev_pitch_name: Optional[str], candidate_pitch_name: str) -> Tuple[float, str]:
    prev_def = _pitch_profile(prev_pitch_name)
    cand_def = _pitch_profile(candidate_pitch_name)
    if not prev_def or not cand_def:
        return 0.0, ""
    if prev_def.key == cand_def.key:
        return -2.5, "(same look)"

    velocity_delta = abs(prev_def.velocity_base - cand_def.velocity_base)
    horiz_delta = abs(prev_def.break_horizontal - cand_def.break_horizontal)
    vert_delta = abs(prev_def.break_vertical - cand_def.break_vertical)

    vel_score = _score_velocity_delta(velocity_delta)
    horiz_score = _score_horizontal_delta(prev_def.break_horizontal, cand_def.break_horizontal, horiz_delta)
    vert_score = _score_vertical_delta(prev_def.break_vertical, cand_def.break_vertical, vert_delta)

    total = vel_score + horiz_score + vert_score
    if not total:
        return 0.0, ""
    tag = f"(synergy {total:+.1f})"
    return total, tag


def _score_velocity_delta(delta: float) -> float:
    if delta < 4:
        return -0.5
    if delta < 7:
        return 0.6
    if delta < 15:
        return 2.3
    if delta < 22:
        return 3.2
    return 3.8


def _score_horizontal_delta(prev_break: float, cand_break: float, delta: float) -> float:
    if abs(prev_break) < 0.5 and abs(cand_break) < 0.5:
        return 0.0
    if prev_break == 0 and cand_break == 0:
        return 0.0
    if prev_break * cand_break < 0:
        return 2.5 + min(1.5, delta * 0.15)
    if delta >= 8:
        return 1.2
    if delta >= 4:
        return 0.6
    return 0.1


def _score_vertical_delta(prev_break: float, cand_break: float, delta: float) -> float:
    crosses_eye = (prev_break >= 0 and cand_break <= -2) or (cand_break >= 0 and prev_break <= -2)
    base = delta * 0.18
    if crosses_eye:
        base += 2.0
    return min(3.0, base)
