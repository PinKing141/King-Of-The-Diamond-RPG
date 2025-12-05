from types import SimpleNamespace

from match_engine.pitch_logic import _call_with_umpire_bias, rng
from match_engine.pregame import UmpireProfile


def _make_catcher(fielding, leadership=60, discipline=60, throwing=60):
    return SimpleNamespace(
        position="Catcher",
        fielding=fielding,
        catcher_leadership=leadership,
        discipline=discipline,
        throwing=throwing,
    )


def _base_state(home_catcher, away_catcher):
    state = SimpleNamespace()
    state.top_bottom = "Top"
    state.home_team = SimpleNamespace(id=1, name="Home")
    state.away_team = SimpleNamespace(id=2, name="Away")
    state.home_lineup = [home_catcher]
    state.away_lineup = [away_catcher]
    state.balls = 0
    state.strikes = 0
    state.umpire_mood = 0.0
    state.umpire_plate_summary = {
        "offense": {"favored": 0, "squeezed": 0},
        "defense": {"favored": 0, "squeezed": 0},
    }
    state.umpire_call_tilt = {
        state.home_team.id: {"favored": 0, "squeezed": 0},
        state.away_team.id: {"favored": 0, "squeezed": 0},
    }
    state.umpire_recent_calls = []
    state.inning = 3
    return state


def _steady_umpire(**overrides):
    profile = UmpireProfile(
        name="Test Ump",
        zone_bias=overrides.get("zone_bias", -1.0),
        home_bias=0.0,
        temperament=overrides.get("temperament", 0.3),
        description="",
        weight=1.0,
    )
    profile.strictness = overrides.get("strictness", 0.5)
    profile.consistency = overrides.get("consistency", 0.9)
    profile.framing_factor = overrides.get("framing_factor", 0.65)
    return profile


def test_framing_bonus_helps_borderline_calls(monkeypatch):
    good = _make_catcher(fielding=85, leadership=80, discipline=70, throwing=65)
    poor = _make_catcher(fielding=40, leadership=35, discipline=40, throwing=35)
    state_good = _base_state(good, poor)
    state_poor = _base_state(poor, good)
    state_good.umpire = _steady_umpire()
    state_poor.umpire = _steady_umpire()

    monkeypatch.setattr(rng, "uniform", lambda _lo, _hi: 0.0)

    good_call, _ = _call_with_umpire_bias(state_good, "Chase")
    poor_call, _ = _call_with_umpire_bias(state_poor, "Chase")

    assert good_call == "Strike"
    assert poor_call == "Ball"


def test_consistency_limits_call_variance(monkeypatch):
    catcher = _make_catcher(fielding=60)
    noisy_state = _base_state(catcher, catcher)
    calm_state = _base_state(catcher, catcher)
    noisy_state.umpire = _steady_umpire(zone_bias=0.75, strictness=0.4, framing_factor=0.0, consistency=0.25)
    calm_state.umpire = _steady_umpire(zone_bias=0.75, strictness=0.4, framing_factor=0.0, consistency=0.98)

    monkeypatch.setattr(rng, "uniform", lambda lo, _hi: lo)

    noisy_call, _ = _call_with_umpire_bias(noisy_state, "Zone")
    calm_call, _ = _call_with_umpire_bias(calm_state, "Zone")

    assert noisy_call == "Ball"
    assert calm_call == "Strike"
