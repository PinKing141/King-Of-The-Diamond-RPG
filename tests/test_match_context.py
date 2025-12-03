from tests.factories import make_basic_match_state
from match_engine.inning_flow import rotate_lineup


def test_runner_tracking_updates_bases():
    state = make_basic_match_state()
    runner = state.home_lineup[0]
    state.runners[0] = runner
    assert state.runners[0] is runner

    state.clear_bases()
    assert all(slot is None for slot in state.runners)


def test_lineup_rotation_moves_to_next_batter():
    state = make_basic_match_state()
    first_batter = state.away_lineup[0]
    rotated = rotate_lineup(state.away_lineup)
    assert rotated[-1] is first_batter
    assert rotated[0] is state.away_lineup[1]
