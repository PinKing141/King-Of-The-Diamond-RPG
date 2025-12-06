from types import SimpleNamespace
from unittest.mock import patch

from match_engine.controller import run_match


def test_run_match_forwards_tournament_name_to_prepare_match():
    captured = {}
    fake_state = SimpleNamespace(event_bus=None, telemetry_store_in_db=False)
    fake_session = SimpleNamespace(close=lambda: None)

    with (
        patch("match_engine.controller.get_session", return_value=fake_session),
        patch("match_engine.controller.prepare_match") as prepare_mock,
        patch("match_engine.controller.CommentaryListener"),
        patch("match_engine.controller.render_box_score_panel"),
        patch("match_engine.controller.save_game_results"),
        patch("match_engine.controller.Scoreboard") as ScoreboardMock,
        patch("match_engine.controller.MatchController") as ControllerMock,
    ):
        ScoreboardMock.return_value = SimpleNamespace()

        def _fake_prepare(home_id, away_id, db_session, clutch_pitch=None, tournament_name=None):
            captured["tournament_name"] = tournament_name
            return fake_state

        prepare_mock.side_effect = _fake_prepare
        controller_instance = ControllerMock.return_value
        controller_instance.start_game.return_value = None

        run_match(1, 2, tournament_name="Summer Koshien", fast=True)

    assert captured.get("tournament_name") == "Summer Koshien"
