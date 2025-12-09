from core.event_bus import EventBus
from ui.match_commentary import CommentaryListener, set_commentary_enabled
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


def test_minigame_events_emit_plain_text(capsys):
    set_commentary_enabled(True)
    bus = EventBus()
    CommentaryListener(bus)  # no IO provided

    trigger_payload = {
        "team_name": "Home",
        "team_side": "home",
        "context": {"inning": 9, "half": "Top", "count": "3-2", "score_diff": 0, "runners_on": 2},
    }
    resolve_payload = {"quality": 0.87, "target_window": 0.18, "feedback": "Painted"}

    bus.publish(EventType.PITCH_MINIGAME_TRIGGER.value, trigger_payload)
    bus.publish(EventType.PITCH_MINIGAME_RESOLVE.value, resolve_payload)

    out = capsys.readouterr().out
    assert "Showtime alert" in out
    assert "Showtime pitch quality" in out
