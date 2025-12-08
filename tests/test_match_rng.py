import random

from match_engine.match_sim import MatchSimulation


class DummyState:
    def __init__(self):
        self.rng = None


def test_match_sim_uses_provided_rng():
    rng = random.Random(12345)
    state = DummyState()
    sim = MatchSimulation(state, rng=rng)

    # Ensure simulation keeps the provided RNG and still exposes it
    assert sim.rng is rng
    assert abs(sim.rng.random() - 0.4166198725) < 1e-6


def test_match_sim_defaults_to_state_rng_when_missing_argument():
    state = DummyState()
    state.rng = random.Random(54321)
    sim = MatchSimulation(state)

    assert sim.rng is state.rng
    expected_first = random.Random(54321).random()
    assert abs(sim.rng.random() - expected_first) < 1e-9
