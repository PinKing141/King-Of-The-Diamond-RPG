import pytest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

from match_engine.match_sim import MatchSimulation, MatchState, PlayOutcome


@pytest.fixture
def mock_game_state():
    """Creates a minimal GameState object required for the simulation."""
    home_pitcher = SimpleNamespace(id=1, control=50, velocity=130, breaking_ball=50)
    batter = SimpleNamespace(id=10, name="Test Batter", contact=50, power=50, team_id=2)

    state = SimpleNamespace(
        top_bottom="Top",
        inning=1,
        balls=0,
        strikes=0,
        outs=0,
        home_score=0,
        away_score=0,
        home_pitcher=home_pitcher,
        home_lineup=[SimpleNamespace(id=99, position="Catcher")],
        away_lineup=[batter],
        away_pitcher=SimpleNamespace(id=20),
        get_stats=lambda _: {"hits": 0, "walks": 0, "strikeouts_pitched": 0},
        play_mode="SIM",
        fast_sim=False,
        human_team_ids={1},
        runners=[None, None, None],
    )
    return state


def test_simulation_starts_waiting(mock_game_state):
    """Ensure the loop starts in the correct state."""
    sim = MatchSimulation(mock_game_state)
    assert sim.loop_state == MatchState.WAITING_FOR_PITCH
    assert sim._current_matchup is None


def test_step_initializes_matchup(mock_game_state):
    """First step should build the matchup context but not execute the play."""
    sim = MatchSimulation(mock_game_state)
    outcome = sim.step()

    assert outcome is None
    assert sim._current_matchup is not None
    assert sim._current_matchup.batter.name == "Test Batter"
    assert sim.loop_state == MatchState.WAITING_FOR_PITCH


def test_step_executes_play_resolution(mock_game_state):
    """
    Second step should trigger execution.
    We verify the first step yields None (matchup build) and the second yields outcome.
    """
    sim = MatchSimulation(mock_game_state)
    first_step = sim.step()
    assert first_step is None
    assert sim._current_matchup is not None
    assert sim.loop_state == MatchState.WAITING_FOR_PITCH

    with patch("match_engine.match_sim.AtBatStateMachine") as MockSM:
        mock_instance = MockSM.return_value

        with patch.object(sim, "_summarize_outcome") as mock_summary:
            mock_summary.return_value = PlayOutcome(
                inning=1,
                half="Top",
                batter_id=10,
                pitcher_id=1,
                outs_recorded=1,
                runs_scored=0,
                description="Strikeout",
                result_type="strikeout",
                half_complete=False,
                drama_level=0,
                batting_team="away",
                fielding_team="home",
            )

            outcome = sim.step()

            assert outcome is not None
            assert outcome.result_type == "strikeout"
            assert sim.loop_state == MatchState.WAITING_FOR_PITCH


def test_autosave_trigger_on_drama(mock_game_state):
    """Ensure high drama plays trigger an autosave checkpoint."""
    sim = MatchSimulation(mock_game_state)
    sim.step()

    with patch("match_engine.match_sim.AtBatStateMachine"), \
         patch.object(sim, "_summarize_outcome") as mock_summary, \
         patch("match_engine.match_sim.autosave_match_state") as mock_autosave:

        mock_summary.return_value = PlayOutcome(
            inning=9,
            half="Bot",
            batter_id=10,
            pitcher_id=1,
            outs_recorded=0,
            runs_scored=1,
            description="Walk-off!",
            result_type="hit",
            half_complete=True,
            drama_level=5,
            batting_team="home",
            fielding_team="away",
        )

        sim.step()

        mock_autosave.assert_called()
