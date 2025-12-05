import importlib
from types import SimpleNamespace

from core.event_bus import EventBus
from match_engine.states import EventType

from battery_system import battery_negotiation as negotiation
from battery_system import battery_trust
from game.catcher_ai import CatcherMemory


def _stub_pitcher(team_id=99):
    return SimpleNamespace(id=1, team_id=team_id, school_id=team_id)


def _stub_catcher(team_id=99):
    return SimpleNamespace(id=2, team_id=team_id, school_id=team_id)


def _stub_batter(team_id=42):
    return SimpleNamespace(id=3, team_id=team_id, school_id=team_id)


def test_run_battery_negotiation_forced_call():
    bus = EventBus()
    events = {"sign": [], "shake": [], "forced": []}
    bus.subscribe(EventType.BATTERY_SIGN_CALLED.value, lambda payload: events["sign"].append(dict(payload)))
    bus.subscribe(EventType.BATTERY_SHAKE.value, lambda payload: events["shake"].append(dict(payload)))
    bus.subscribe(EventType.BATTERY_FORCED_CALL.value, lambda payload: events["forced"].append(dict(payload)))

    state = SimpleNamespace(
        event_bus=bus,
        pitcher_presence={1: 0.0},
        catcher_memory=CatcherMemory(),
        battery_trust_cache={(1, 2): 40},
        battery_sync={(1, 2): 0.0},
    )
    battery_trust.set_trust_snapshot(state, 1, 2, 40)

    negotiation_module = importlib.reload(negotiation)
    assert negotiation_module._player_team_id(_stub_pitcher()) != 1

    # Force the AI pitcher to reject every sign so the catcher must eventually force the call.
    decision_invocations: list[int] = []

    def always_shake(*args, **kwargs):
        decision_invocations.append(1)
        return False

    class DummySignGenerator:
        def __init__(self):
            self.calls = 0

        def __call__(self, *_, **__):
            self.calls += 1
            pitch = SimpleNamespace(pitch_name=f"Pitch{self.calls}")
            return SimpleNamespace(
                pitch=pitch,
                location="Zone",
                intent="Normal",
                confidence=0.9,
                reason=f"seq {self.calls}",
            )

    sign_generator = DummySignGenerator()

    result = negotiation_module.run_battery_negotiation(
        _stub_pitcher(),
        _stub_catcher(),
        _stub_batter(),
        state,
        decision_override=always_shake,
        sign_override=sign_generator,
    )

    assert decision_invocations
    assert result.forced is True
    assert len(events["forced"]) == 1
    assert events["forced"][0]["forced"] is True
    assert events["sign"][0]["phase"] == "initial"
    assert events["sign"][-1]["phase"] == "forced"
    assert len(events["shake"]) == result.shakes
    assert result.shakes >= 1


def test_apply_plate_result_to_trust_updates_cache(monkeypatch):
    state = SimpleNamespace(battery_trust_cache={}, battery_sync={})
    calls: list[tuple[int, int, str]] = []

    def fake_update(pid, cid, token):
        calls.append((pid, cid, token))
        return 77

    monkeypatch.setattr(battery_trust, "update_trust_after_at_bat", fake_update)

    new_value = battery_trust.apply_plate_result_to_trust(
        state,
        pitcher_id=5,
        catcher_id=9,
        result_type="strikeout",
        hit_type=None,
    )

    assert new_value == 77
    assert calls == [(5, 9, "K")]
    assert state.battery_trust_cache[(5, 9)] == 77

    # No recognized result -> no DB call
    calls.clear()
    assert (
        battery_trust.apply_plate_result_to_trust(
            state,
            pitcher_id=5,
            catcher_id=9,
            result_type="out_in_play",
            hit_type=None,
        )
        is None
    )
    assert calls == []
