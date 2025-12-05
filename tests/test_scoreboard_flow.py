from __future__ import annotations

from types import SimpleNamespace

from core.event_bus import EventBus
from match_engine.controller import MatchController
from match_engine.scoreboard import Scoreboard


class DummyScoreboard(Scoreboard):
    def print_board(self, state):  # pragma: no cover - suppress console noise
        return None


def make_controller(monkeypatch, run_hook=None):
    from match_engine import controller as controller_module

    outs_log = []

    class StubAtBat:
        def __init__(self, state):
            self.state = state

        def run(self):
            outs_log.append(self.state.outs)
            self.state.outs += 1
            if callable(run_hook):
                run_hook(self.state)

    monkeypatch.setattr(controller_module, "AtBatStateMachine", lambda state: StubAtBat(state))

    state = SimpleNamespace(
        inning=1,
        home_score=0,
        away_score=0,
        top_bottom="Top",
        outs=0,
        runners=[None, None, None],
        home_team=SimpleNamespace(id=1, name="Home"),
        away_team=SimpleNamespace(id=2, name="Away"),
        home_lineup=[SimpleNamespace(id=i, name=f"H{i}") for i in range(1, 10)],
        away_lineup=[SimpleNamespace(id=i + 20, name=f"A{i}") for i in range(1, 10)],
        event_bus=EventBus(),
    )
    def _clear_bases():
        state.runners = [None, None, None]

    state.clear_bases = _clear_bases
    return MatchController(state, DummyScoreboard()), outs_log


def test_out_progression_resets_between_halves(monkeypatch):
    controller, outs_log = make_controller(monkeypatch)

    controller._execute_half_inning("Top")
    assert outs_log[:3] == [0, 1, 2]

    controller._execute_half_inning("Bot")
    assert outs_log[3:] == [0, 1, 2]


def test_inning_flips_after_top_half(monkeypatch):
    controller, _ = make_controller(monkeypatch)

    controller._execute_half_inning("Top")
    assert controller.state.top_bottom == "Top"

    controller._execute_half_inning("Bot")
    assert controller.state.top_bottom == "Bot"


def test_scoreboard_records_each_inning(monkeypatch):
    controller, _ = make_controller(monkeypatch)

    controller._run_inning()
    assert len(controller.scoreboard.innings) == 1

    controller.state.inning += 1
    controller._run_inning()
    assert len(controller.scoreboard.innings) == 2


def test_run_logging_tracks_correct_team():
    board = Scoreboard()
    board.record_inning(1, away_runs=3, home_runs=2)
    assert board.innings[0] == [3, 2]


def test_error_logging_records_position_codes():
    board = Scoreboard()
    board.record_error("home", position="Shortstop", error_type="E_THROW", runs_scored=2)
    board.record_error("away", position="Left Field", error_type="E_FIELD", runs_scored=0)
    assert [entry["tag"] for entry in board.error_log["home"]] == ["E6(T)"]
    assert [entry["tag"] for entry in board.error_log["away"]] == ["E7"]
    summary = board.get_error_summary()
    assert summary["home"] == [{"tag": "E6(T)", "rbis": 2, "position": "Shortstop", "type": "E_THROW"}]
    assert summary["away"] == [{"tag": "E7", "rbis": 0, "position": "Left Field", "type": "E_FIELD"}]
