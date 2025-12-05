from __future__ import annotations

from core.event_bus import EventBus
from match_engine.pitch_logic import _apply_clutch_bonus
from match_engine.pregame import _apply_clutch_pitch_payload
from match_engine.states import EventType
from tests.factories import make_basic_match_state


class StubMomentum:
    def __init__(self) -> None:
        self.calls: list[tuple[int | None, int | None]] = []

    def record_event(self, team_id, event_key, delta=None):
        self.calls.append((team_id, delta))
        # Mirror MomentumSystem API by returning current meter placeholder
        return int(delta or 0)


def _subscribe(bus: EventBus, event_name: str) -> list[dict]:
    events: list[dict] = []

    def _collector(payload):
        events.append(dict(payload))

    bus.subscribe(event_name, _collector)
    return events


def test_clutch_payload_boosts_pitcher_and_momentum():
    state = make_basic_match_state()
    state.momentum_system = StubMomentum()

    start_events = _subscribe(state.event_bus, EventType.PITCH_MINIGAME_TRIGGER.value)
    resolve_events = _subscribe(state.event_bus, EventType.PITCH_MINIGAME_RESOLVE.value)

    payload = {
        "team_id": state.home_team.id,
        "team_name": state.home_team.name,
        "team_side": "home",
        "quality": 0.9,
        "feedback": "Filthy",
        "deviation": 0.05,
        "difficulty": 0.4,
        "context": {"inning": 8, "half": "Top", "count": "3-2", "label": "Elite"},
    }
    state.clutch_pitch_payload = payload
    base_confidence = state.confidence_map[state.home_pitcher.id]

    _apply_clutch_pitch_payload(state)

    # Confidence rises for the selected pitcher
    assert state.confidence_map[state.home_pitcher.id] == base_confidence + 5
    # Momentum delta recorded for the correct team
    assert state.momentum_system.calls == [(state.home_team.id, 4)]
    # Pending clutch effect queued for later consumption
    assert state.clutch_pitch_effects.get(state.home_team.id)
    # Start and resolve events echo through the bus
    assert start_events and start_events[0]["team_id"] == state.home_team.id
    assert resolve_events and resolve_events[0]["quality"] == 0.9
    # Log entry was appended for telemetry
    assert any("Pitch minigame quality" in entry for entry in state.logs)


def test_clutch_payload_handles_negative_outcome():
    state = make_basic_match_state()
    state.momentum_system = StubMomentum()

    payload = {
        "team_id": state.away_team.id,
        "team_name": state.away_team.name,
        "team_side": "away",
        "quality": 0.1,
        "feedback": "Meatball",
        "deviation": 0.4,
        "difficulty": 0.6,
        "context": {"inning": 9, "half": "Bot", "count": "2-1", "label": "Collapse"},
    }
    state.clutch_pitch_payload = payload
    base_confidence = state.confidence_map[state.away_pitcher.id]

    _apply_clutch_pitch_payload(state)

    # Negative quality drags confidence down
    assert state.confidence_map[state.away_pitcher.id] == base_confidence - 5
    # Momentum swings toward opponent (negative delta)
    assert state.momentum_system.calls == [(state.away_team.id, -4)]


def test_clutch_payload_consumption_respects_half_inning():
    state = make_basic_match_state()
    payload = {
        "team_id": state.home_team.id,
        "team_name": state.home_team.name,
        "team_side": "home",
        "quality": 0.8,
        "context": {"inning": 9, "half": "Top", "count": "3-2", "label": "Test"},
    }
    state.queue_clutch_pitch_payload(payload)
    consumed = state.consume_clutch_pitch_effect(state.home_pitcher.id)
    assert consumed["team_id"] == state.home_team.id

    # Requeue and flip half so home is batting; effect should not apply
    state.queue_clutch_pitch_payload(payload)
    state.top_bottom = "Bot"
    assert state.consume_clutch_pitch_effect(state.home_pitcher.id) is None


def test_apply_clutch_bonus_pushes_control_extremes():
    ctrl, mov, velo, special = _apply_clutch_bonus(60.0, 30.0, 90.0, 0.95)
    assert ctrl > 70.0 and mov > 35.0
    assert special == "clutch_paint"

    ctrl_bad, mov_bad, _, special_bad = _apply_clutch_bonus(60.0, 30.0, 90.0, 0.1)
    assert ctrl_bad < 55.0 and mov_bad < 30.0
    assert special_bad == "clutch_miss"