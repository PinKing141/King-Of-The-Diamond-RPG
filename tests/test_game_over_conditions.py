from types import SimpleNamespace

from core.event_bus import EventBus
from match_engine.controller import MatchController


class DummyScoreboard:
    def record_inning(self, *args, **kwargs):  # pragma: no cover
        return None

    def print_board(self, state):  # pragma: no cover
        return None


def make_controller(inning, home_score, away_score, top_bottom="Bot", outs=3):
    state = SimpleNamespace(
        inning=inning,
        home_score=home_score,
        away_score=away_score,
        top_bottom=top_bottom,
        outs=outs,
        home_team=SimpleNamespace(id=1, name="Home"),
        away_team=SimpleNamespace(id=2, name="Away"),
        event_bus=EventBus(),
    )
    return MatchController(state, DummyScoreboard())


def test_regulation_game_over_when_home_leads_bottom_ninth():
    controller = make_controller(9, home_score=3, away_score=1)
    assert controller.is_game_over() is True


def test_walkoff_detected_immediately():
    controller = make_controller(9, home_score=4, away_score=3, top_bottom="Bot", outs=1)
    assert controller.is_game_over() is True


def test_extra_innings_continues_when_tied():
    controller = make_controller(9, home_score=2, away_score=2)
    assert controller.is_game_over() is False
