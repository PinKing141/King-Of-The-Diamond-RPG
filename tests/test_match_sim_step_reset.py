import pytest

from match_engine.match_sim import MatchSimulation, MatchupContext
from match_engine.states import InningHalf, MatchState


class FaultySim(MatchSimulation):
    """Test double that forces an exception during matchup execution."""

    def __init__(self):
        super().__init__(state=object())

    def _build_matchup(self):
        pitcher = type("Pitcher", (), {"id": 1})()
        batter = type("Batter", (), {"id": 2})()
        return MatchupContext(
            inning=1,
            half=InningHalf.TOP,
            pitcher=pitcher,
            batter=batter,
            lineup_attr="away_lineup",
            balls=0,
            strikes=0,
            outs_before=0,
            home_score=0,
            away_score=0,
            batter_stats={},
            pitcher_stats={},
            is_human=False,
        )

    def _is_rivalry_moment(self, matchup):
        return False

    def _emit_rival_cut_in(self, matchup):
        return False

    def _select_input_source(self, matchup):
        return "cpu"

    def _execute_matchup(self):
        raise RuntimeError("forced failure during execution")

    def _summarize_outcome(self, outcome):
        return outcome


def test_step_resets_state_after_failure():
    sim = FaultySim()

    # Phase 1 builds the matchup and returns None.
    assert sim.step() is None
    assert sim._current_matchup is not None

    # Phase 2 raises, but internal flags should reset in finally block.
    with pytest.raises(RuntimeError):
        sim.step()

    assert sim._current_matchup is None
    assert sim._pending_cut_in is False
    assert sim._pending_choice is None
    assert sim.awaiting_player_choice is False
    assert sim.loop_state == MatchState.WAITING_FOR_PITCH
