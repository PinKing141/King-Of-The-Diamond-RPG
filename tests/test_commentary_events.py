from types import SimpleNamespace

from core.event_bus import EventBus
from match_engine.batter_logic import _announce, AtBatPhase, AtBatStateMachine


def test_announce_publishes_match_commentary():
    bus = EventBus()
    payloads = []
    bus.subscribe("MATCH_COMMENTARY", payloads.append)

    _announce(bus, "MATCH_COMMENTARY", {"text": "hi"})

    assert payloads and payloads[0]["text"] == "hi"


def test_emit_phase_publishes_phase_event():
    bus = EventBus()
    captured = []
    bus.subscribe("ATBAT_PHASE", captured.append)

    state = SimpleNamespace(event_bus=bus)
    machine = AtBatStateMachine(state)

    machine._emit_phase(AtBatPhase.PITCH, {"marker": 1})

    assert captured and captured[0]["phase"] == "PITCH"
    assert captured[0]["marker"] == 1
