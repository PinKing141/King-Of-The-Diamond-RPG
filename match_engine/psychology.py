from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, TYPE_CHECKING

from core.event_bus import EventBus
from match_engine.states import EventType

if TYPE_CHECKING:  # pragma: no cover - used only for typing
    from match_engine.pitch_logic import PitchResult
    from match_engine.match_sim import PlayOutcome


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class PitcherMentalState:
    focus: float = 0.0
    trauma: float = 0.0
    intimidation: float = 0.0

    def as_modifiers(self) -> Tuple[float, float, float]:
        control = (self.focus * 0.35) - (self.trauma * 0.45)
        movement = (self.focus * 0.15) - (self.trauma * 0.15)
        velocity = self.intimidation * 0.4
        return control, movement, velocity


@dataclass
class BatterMentalState:
    confidence: float = 0.0
    fear: float = 0.0
    poise: float = 0.0

    def eye_contact_scalars(self) -> Tuple[float, float]:
        eye = 1.0 + (self.confidence * 0.015) - (self.fear * 0.02)
        contact = 1.0 + (self.confidence * 0.02) - (self.fear * 0.015)
        eye = _clamp(eye, 0.7, 1.35)
        contact = _clamp(contact, 0.7, 1.35)
        return eye, contact


@dataclass(frozen=True)
class PitcherPsychSnapshot:
    control_bonus: float
    movement_bonus: float
    velocity_bonus: float
    trauma: float
    focus: float


@dataclass(frozen=True)
class BatterPsychSnapshot:
    eye_scalar: float
    contact_scalar: float
    confidence: float
    fear: float


class PsychologyEngine:
    """Tracks emotional momentum for pitchers and batters during a match."""

    def __init__(self, state, *, bus: Optional[EventBus] = None) -> None:
        self.state = state
        self.bus = bus
        self.pitchers: Dict[int, PitcherMentalState] = {}
        self.batters: Dict[int, BatterMentalState] = {}

    def attach_bus(self, bus: EventBus) -> None:
        self.bus = bus

    def _emit_shift(self, payload: Dict[str, object]) -> None:
        if not self.bus:
            return
        self.bus.publish(EventType.PSYCHOLOGY_SHIFT.value, payload)

    def _pitcher_state(self, pitcher_id: Optional[int]) -> Optional[PitcherMentalState]:
        if not pitcher_id:
            return None
        return self.pitchers.setdefault(pitcher_id, PitcherMentalState())

    def _batter_state(self, batter_id: Optional[int]) -> Optional[BatterMentalState]:
        if not batter_id:
            return None
        return self.batters.setdefault(batter_id, BatterMentalState())

    def record_pitch(
        self,
        pitcher_id: Optional[int],
        batter_id: Optional[int],
        result: "PitchResult",
        *,
        leverage: float = 1.0,
    ) -> None:
        pitcher_state = self._pitcher_state(pitcher_id)
        batter_state = self._batter_state(batter_id)
        if not pitcher_state and not batter_state:
            return
        leverage = max(0.5, min(2.5, leverage))
        if pitcher_state:
            if result.outcome == "Strike":
                delta = 0.65 if result.description == "Swinging Miss" else 0.35
                pitcher_state.focus = _clamp(pitcher_state.focus + delta * leverage, -6.0, 8.0)
                pitcher_state.trauma = _clamp(pitcher_state.trauma - 0.25, 0.0, 8.0)
                pitcher_state.intimidation = _clamp(pitcher_state.intimidation + 0.2 * leverage, -4.0, 6.0)
            elif result.outcome == "Ball":
                pitcher_state.focus = _clamp(pitcher_state.focus - 0.45 * leverage, -7.0, 8.0)
                pitcher_state.intimidation = _clamp(pitcher_state.intimidation - 0.3, -4.0, 6.0)
            elif result.outcome == "Foul":
                pitcher_state.focus = _clamp(pitcher_state.focus + 0.1, -7.0, 8.0)
            elif result.outcome == "InPlay":
                quality = getattr(result, "contact_quality", 0)
                if quality >= 35:
                    pitcher_state.trauma = _clamp(pitcher_state.trauma + 0.9 * leverage, 0.0, 10.0)
                    pitcher_state.focus = _clamp(pitcher_state.focus - 0.4 * leverage, -7.0, 8.0)
                else:
                    pitcher_state.focus = _clamp(pitcher_state.focus + 0.2, -7.0, 8.0)
            self._emit_shift(
                {
                    "kind": "pitcher",
                    "pitcher_id": pitcher_id,
                    "focus": pitcher_state.focus,
                    "trauma": pitcher_state.trauma,
                }
            )
        if batter_state:
            if result.outcome == "Strike":
                fear_delta = 0.4 if result.description == "Swinging Miss" else 0.25
                batter_state.fear = _clamp(batter_state.fear + fear_delta * leverage, 0.0, 8.5)
                batter_state.confidence = _clamp(batter_state.confidence - 0.3, -6.0, 7.0)
            elif result.outcome == "Ball":
                batter_state.fear = _clamp(batter_state.fear - 0.35, 0.0, 8.5)
                batter_state.confidence = _clamp(batter_state.confidence + 0.4, -6.0, 7.0)
            elif result.outcome == "Foul":
                batter_state.confidence = _clamp(batter_state.confidence + 0.15, -6.0, 7.0)
            elif result.outcome == "InPlay":
                quality = getattr(result, "contact_quality", 0)
                if quality >= 35:
                    batter_state.confidence = _clamp(batter_state.confidence + 0.9, -6.0, 7.0)
                    batter_state.fear = _clamp(batter_state.fear - 0.5, 0.0, 8.5)
                else:
                    batter_state.confidence = _clamp(batter_state.confidence + 0.3, -6.0, 7.0)
            self._emit_shift(
                {
                    "kind": "batter",
                    "batter_id": batter_id,
                    "confidence": batter_state.confidence,
                    "fear": batter_state.fear,
                }
            )

    def record_plate_outcome(self, outcome: "PlayOutcome") -> None:
        pitcher_state = self._pitcher_state(outcome.pitcher_id)
        batter_state = self._batter_state(outcome.batter_id)
        if not pitcher_state and not batter_state:
            return
        drama = getattr(outcome, "drama_level", 1) or 1
        if pitcher_state:
            if outcome.result_type == "strikeout":
                pitcher_state.focus = _clamp(pitcher_state.focus + 0.9 * drama, -6.0, 8.5)
                pitcher_state.intimidation = _clamp(pitcher_state.intimidation + 0.6 * drama, -4.0, 6.5)
            elif outcome.result_type in {"hit", "run_scored", "double_play"}:
                penalty = 0.6 * drama if outcome.result_type != "double_play" else -0.4
                pitcher_state.focus = _clamp(pitcher_state.focus - penalty, -7.0, 8.5)
                pitcher_state.trauma = _clamp(pitcher_state.trauma + 0.5 * max(1, drama - 1), 0.0, 10.0)
        if batter_state:
            if outcome.result_type == "hit":
                batter_state.confidence = _clamp(batter_state.confidence + 1.1 * drama, -6.0, 8.0)
                batter_state.fear = _clamp(batter_state.fear - 0.6, 0.0, 8.5)
            elif outcome.result_type == "strikeout":
                batter_state.confidence = _clamp(batter_state.confidence - 1.0 * drama, -7.0, 8.0)
                batter_state.fear = _clamp(batter_state.fear + 0.7 * drama, 0.0, 8.5)
        self._emit_shift(
            {
                "kind": "plate_outcome",
                "pitcher_id": outcome.pitcher_id,
                "batter_id": outcome.batter_id,
                "result": outcome.result_type,
                "drama": drama,
            }
        )

    def pitcher_modifiers(self, pitcher_id: Optional[int]) -> PitcherPsychSnapshot:
        state = self.pitchers.get(pitcher_id)
        if not state:
            return PitcherPsychSnapshot(0.0, 0.0, 0.0, 0.0, 0.0)
        control, movement, velocity = state.as_modifiers()
        return PitcherPsychSnapshot(
            control_bonus=control,
            movement_bonus=movement,
            velocity_bonus=velocity,
            trauma=state.trauma,
            focus=state.focus,
        )

    def batter_modifiers(self, batter_id: Optional[int]) -> BatterPsychSnapshot:
        state = self.batters.get(batter_id)
        if not state:
            return BatterPsychSnapshot(1.0, 1.0, 0.0, 0.0)
        eye, contact = state.eye_contact_scalars()
        return BatterPsychSnapshot(
            eye_scalar=eye,
            contact_scalar=contact,
            confidence=state.confidence,
            fear=state.fear,
        )

    def peek_pitcher(self, pitcher_id: Optional[int]) -> Optional[PitcherMentalState]:
        return self.pitchers.get(pitcher_id)

    def peek_batter(self, batter_id: Optional[int]) -> Optional[BatterMentalState]:
        return self.batters.get(batter_id)


__all__ = [
    "PsychologyEngine",
    "PitcherPsychSnapshot",
    "BatterPsychSnapshot",
]
