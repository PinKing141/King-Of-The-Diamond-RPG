from types import SimpleNamespace

import pytest

from core.event_bus import EventBus

from match_engine.controller import MatchController, _finalize_rivalry_context
from world.rivals import Rival, RivalMatchContext

from match_engine.controller import MatchController



class DummyScoreboard:
    def __init__(self):
        self.records = []

    def record_inning(self, *args, **kwargs):
        self.records.append((args, kwargs))

    def print_board(self, state):
        return None


def _build_state(inning: int, home_score: int, away_score: int):
    bus = EventBus()
    home_team = SimpleNamespace(id=1, name="Home")
    away_team = SimpleNamespace(id=2, name="Away")
    state = SimpleNamespace(
        inning=inning,
        home_score=home_score,
        away_score=away_score,
        top_bottom="Top",
        event_bus=bus,
        home_team=home_team,
        away_team=away_team,
    )
    return state, bus


def test_regulation_win_stops_game():
    state, bus = _build_state(inning=9, home_score=3, away_score=1)
    events = []

    def _capture(payload):
        events.append(payload)

    bus.subscribe("MATCH_STATE_CHANGE", _capture)
    controller = MatchController(state, DummyScoreboard())

    assert controller._should_continue() is False
    assert events == []


def test_extra_innings_triggers_event():
    state, bus = _build_state(inning=9, home_score=2, away_score=2)
    events = []
    bus.subscribe("MATCH_STATE_CHANGE", lambda payload: events.append(payload))

    controller = MatchController(state, DummyScoreboard())

    assert controller._should_continue() is True
    assert events[-1]["phase"] == "EXTRA_INNINGS"


def test_draw_condition_emits_draw_event():
    state, bus = _build_state(inning=12, home_score=4, away_score=4)
    events = []
    bus.subscribe("MATCH_STATE_CHANGE", lambda payload: events.append(payload))

    controller = MatchController(state, DummyScoreboard())

    assert controller._should_continue() is False
    assert events[-1]["phase"] == "DRAW"



def test_finalize_rivalry_context_records_summary():
    rival = Rival(hero_id=10, rival_id=22)
    ctx = RivalMatchContext(rival=rival, hero_team_id=1, rival_team_id=2)
    ctx.begin_match()
    state = SimpleNamespace(
        rival_match_context=ctx,
        hero_name="Akira",
        rival_name="Daigo",
        hero_school_id=1,
        logs=[],
        rival_postgame=None,
    )

    _finalize_rivalry_context(state, winner_team_id=1)

    assert state.rival_postgame
    assert state.rival_postgame["result"] == "hero_win"
    assert any("Akira vs Daigo" in line for line in state.logs)

