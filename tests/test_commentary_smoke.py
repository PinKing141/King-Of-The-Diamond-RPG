import builtins
from match_engine import commentary


class DummyBus:
    def subscribe(self, *_args, **_kwargs):
        return None


def test_lineup_ready_outputs_when_enabled(capsys):
    commentary.set_commentary_enabled(True)
    listener = commentary.CommentaryListener(event_bus=None)
    payload = {
        "home": {"team_name": "Home", "lineup": []},
        "away": {"team_name": "Away", "lineup": []},
    }
    listener._on_lineup_ready(payload)  # smoke: should print without error
    out = capsys.readouterr().out
    assert "LINEUP CARD" in out
    assert "Play ball" in out


def test_lineup_ready_silent_when_disabled(capsys):
    commentary.set_commentary_enabled(False)
    listener = commentary.CommentaryListener(event_bus=None)
    payload = {
        "home": {"team_name": "Home", "lineup": []},
        "away": {"team_name": "Away", "lineup": []},
    }
    listener._on_lineup_ready(payload)
    out = capsys.readouterr().out
    assert out.strip() == ""
