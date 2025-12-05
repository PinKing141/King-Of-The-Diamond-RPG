"""Phase 3 baserunning helpers.

This module exposes light-weight primitives so both the match engine and the
world simulator can reason about runner pressure.  It intentionally avoids
referencing heavy gameplay systems beyond the EventBus/EventType surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from game.rng import get_rng
from match_engine.states import EventType

rng = get_rng()

# ---------------------------------------------------------------------------
# Dataclasses


@dataclass
class RunnerThreatState:
    runner: object
    base_index: int
    lead_off_distance: float
    jump_quality: float
    runner_speed_time: float
    pressure: float
    last_pitch_tag: int = 0

    def adjust_lead(self, delta: float) -> None:
        self.lead_off_distance = max(2.0, self.lead_off_distance + delta)

    def adjust_jump(self, delta: float) -> None:
        self.jump_quality = max(-3.0, self.jump_quality + delta)


@dataclass
class SlideStepResult:
    used_slide_step: bool
    delivery_time: float
    control_penalty: float
    velocity_penalty: float
    stamina_cost: float


@dataclass
class StealOutcome:
    success: bool
    time_delta: float
    description: str


@dataclass
class PickoffOutcome:
    attempted: bool
    picked_runner: bool
    stamina_cost: float
    lead_adjustment: float
    description: str


# ---------------------------------------------------------------------------
# Cached threat helpers


def _threat_cache(container) -> Dict[Tuple[int, int], RunnerThreatState]:
    cache = getattr(container, "base_threat_cache", None)
    if cache is None:
        cache = {}
        setattr(container, "base_threat_cache", cache)
    return cache


def _runner_speed_time(runner) -> float:
    speed = getattr(runner, "speed", getattr(runner, "running", 50)) or 50
    return max(3.0, 3.75 - (speed - 50) * 0.015)


def prepare_runner_state(state, base_index: int) -> Optional[RunnerThreatState]:
    runners = getattr(state, "runners", None)
    if not runners or base_index >= len(runners):
        return None
    runner = runners[base_index]
    if not runner:
        return None
    cache = _threat_cache(state)
    key = (getattr(runner, "id", id(runner)), base_index)
    threat = cache.get(key)
    if threat is None:
        base_lead = 7.0 + rng.uniform(-0.4, 1.2)
        awareness = getattr(runner, "awareness", 50) or 50
        jump = 1.5 + (awareness - 50) * 0.03 + rng.uniform(-1.0, 1.25)
        pressure = getattr(state, "crowd_intensity", 0.0) * 0.1
        threat = RunnerThreatState(
            runner=runner,
            base_index=base_index,
            lead_off_distance=max(4.5, base_lead),
            jump_quality=max(-1.5, jump),
            runner_speed_time=_runner_speed_time(runner),
            pressure=pressure,
        )
        cache[key] = threat
    return threat


# ---------------------------------------------------------------------------
# Slide step + timing helpers


def _base_delivery_time(pitcher) -> float:
    delivery = getattr(pitcher, "delivery_time", None)
    if delivery:
        return delivery
    control = getattr(pitcher, "control", 50) or 50
    athleticism = getattr(pitcher, "athleticism", getattr(pitcher, "mechanics", 50)) or 50
    return max(1.2, 1.55 - (control - 50) * 0.002 - (athleticism - 50) * 0.0015)


def _catcher_pop_time(catcher) -> float:
    if not catcher:
        return 2.05
    arm = getattr(catcher, "throwing", 50) or 50
    release = getattr(catcher, "release", getattr(catcher, "mechanics", 50)) or 50
    return max(1.75, 2.05 - (arm - 50) * 0.003 - (release - 50) * 0.002)


def evaluate_slide_step(pitcher, *, use_slide_step: bool, fatigue_level: float = 0.0) -> SlideStepResult:
    base_delivery = _base_delivery_time(pitcher)
    stamina_penalty = max(0.0, fatigue_level) * 0.02
    if not use_slide_step:
        return SlideStepResult(
            used_slide_step=False,
            delivery_time=base_delivery + stamina_penalty,
            control_penalty=0.0,
            velocity_penalty=0.0,
            stamina_cost=0.25 if fatigue_level > 0.5 else 0.0,
        )

    delivery_time = max(1.0, base_delivery - 0.18)
    velocity_penalty = 1.5 + fatigue_level * 0.5
    control_penalty = 4.0 + fatigue_level * 1.5
    stamina_cost = 1.0 + fatigue_level * 0.25
    return SlideStepResult(
        used_slide_step=True,
        delivery_time=delivery_time,
        control_penalty=control_penalty,
        velocity_penalty=velocity_penalty,
        stamina_cost=stamina_cost,
    )


# ---------------------------------------------------------------------------
# Steal + pickoff resolution


def _lead_advantage(threat: RunnerThreatState) -> float:
    return threat.lead_off_distance * 0.02 + threat.jump_quality * 0.03 - threat.pressure * 0.02


def _publish(state, event: EventType, payload: dict) -> None:
    bus = getattr(state, "event_bus", None)
    if not bus:
        return
    bus.publish(event.value, payload)


def resolve_steal_attempt(
    state,
    *,
    threat: RunnerThreatState,
    pitcher,
    catcher,
    delivery_time: Optional[float] = None,
    pop_time: Optional[float] = None,
) -> StealOutcome:
    delivery = delivery_time or _base_delivery_time(pitcher)
    pop = pop_time or _catcher_pop_time(catcher)
    runner_time = threat.runner_speed_time
    lead_adv = _lead_advantage(threat)
    defense_time = delivery + pop + rng.uniform(-0.05, 0.05)
    offense_time = runner_time - lead_adv
    success = defense_time > offense_time
    time_delta = defense_time - offense_time

    description = "SAFELY steals" if success else "OUT attempting to steal"
    _publish(
        state,
        EventType.BASERUN_STEAL,
        {
            "runner_id": getattr(threat.runner, "id", None),
            "base": threat.base_index,
            "success": success,
            "time_delta": time_delta,
        },
    )
    return StealOutcome(success=success, time_delta=time_delta, description=description)


def simulate_pickoff(state, *, threat: RunnerThreatState, pitcher) -> PickoffOutcome:
    pick_skill = getattr(pitcher, "pickoff_rating", getattr(pitcher, "control", 50)) or 50
    lead = threat.lead_off_distance
    base_chance = 0.05 + (pick_skill - 50) * 0.004 + (lead - 7.0) * 0.02
    base_chance = min(0.35, max(0.02, base_chance))
    roll = rng.random()
    picked = roll < base_chance
    lead_adjustment = -1.0 if picked else -0.5
    threat.adjust_lead(lead_adjustment)
    stamina_cost = 0.75 + max(0.0, pick_skill - 50) * 0.01
    _publish(
        state,
        EventType.BASERUN_PICKOFF,
        {
            "runner_id": getattr(threat.runner, "id", None),
            "base": threat.base_index,
            "picked": picked,
            "lead": threat.lead_off_distance,
        },
    )
    description = "Picked off!" if picked else "Runner dives back safely."
    return PickoffOutcome(
        attempted=True,
        picked_runner=picked,
        stamina_cost=stamina_cost,
        lead_adjustment=lead_adjustment,
        description=description,
    )


def note_runner_pressure(state, threat: RunnerThreatState) -> None:
    _publish(
        state,
        EventType.BASERUN_THREAT,
        {
            "runner_id": getattr(threat.runner, "id", None),
            "base": threat.base_index,
            "lead": threat.lead_off_distance,
            "jump": threat.jump_quality,
        },
    )


__all__ = [
    "RunnerThreatState",
    "SlideStepResult",
    "StealOutcome",
    "PickoffOutcome",
    "prepare_runner_state",
    "evaluate_slide_step",
    "resolve_steal_attempt",
    "simulate_pickoff",
    "note_runner_pressure",
]
