from core.event_bus import EventBus
from match_engine.commentary import CommentaryListener, set_commentary_enabled
from match_engine.states import EventType


def _make_payload(**overrides):
    payload = {
        "pitcher_id": 101,
        "catcher_id": 202,
        "batter_id": 303,
        "pitch_name": "Slider",
        "location": "Chase",
        "intent": "Expand",
        "trust": 64,
        "sync": 0.25,
        "shakes_used": 0,
        "shakes_allowed": 3,
        "phase": "initial",
        "reason": "Batter chasing spin",
    }
    payload.update(overrides)
    return payload


def test_battery_sign_event_outputs_banner(capsys):
    set_commentary_enabled(True)
    bus = EventBus()
    CommentaryListener(bus)
    bus.publish(EventType.BATTERY_SIGN_CALLED.value, _make_payload())
    out = capsys.readouterr().out
    assert "Catcher Sign" in out
    assert "Slider" in out
    assert "Trust" in out


def test_battery_shake_event_outputs_warning(capsys):
    set_commentary_enabled(True)
    bus = EventBus()
    CommentaryListener(bus)
    bus.publish(
        EventType.BATTERY_SHAKE.value,
        _make_payload(shakes_used=1, sync=-0.4),
    )
    out = capsys.readouterr().out
    assert "Shake-Off" in out
    assert "1/3" in out


def test_battery_forced_event_outputs_alert(capsys):
    set_commentary_enabled(True)
    bus = EventBus()
    CommentaryListener(bus)
    bus.publish(EventType.BATTERY_FORCED_CALL.value, _make_payload(sync=-1.5))
    out = capsys.readouterr().out
    assert "Forced Call" in out
    assert "-1.50" in out
