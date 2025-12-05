from __future__ import annotations

from types import SimpleNamespace

import world_sim.fielding_engine as engine


POSITION_COORDS = {
    "pitcher": (0.0, 57.5),
    "catcher": (0.0, -8.0),
    "first base": (63.5, 63.5),
    "second base": (0.0, 127.0),
    "shortstop": (-35.0, 115.0),
    "third base": (-63.5, 63.5),
    "left field": (-185.0, 215.0),
    "center field": (0.0, 250.0),
    "right field": (185.0, 215.0),
}


def _make_snap(position: str, *, rating: int = 70, reliability: int | None = None) -> engine.FielderSnapshot:
    x, y = POSITION_COORDS[position.lower()]
    return engine.FielderSnapshot(
        player=SimpleNamespace(name=position),
        position=position,
        x=x,
        y=y,
        speed_rating=rating,
        reaction_rating=rating,
        reliability_rating=reliability if reliability is not None else rating,
        arm_rating=rating,
    )


def test_simulate_batted_ball_marks_home_run():
    ball = engine.simulate_batted_ball(110, 32, 0)
    assert ball.is_home_run is True


def test_fly_ball_secured_when_fielder_arrives():
    ball = engine.simulate_batted_ball(95, 28, 0)
    snap = _make_snap("Center Field", rating=85)
    result = engine.resolve_fielding_play(ball, [snap], runner_speed=55)
    assert result.hit_type == "Out"
    assert result.caught is True


def test_grounder_beats_slow_runner():
    ball = engine.simulate_batted_ball(88, 4, -5)
    snap = _make_snap("Shortstop", rating=80)
    result = engine.resolve_fielding_play(ball, [snap], runner_speed=35)
    assert result.hit_type == "Out"
    assert result.throw_completed is True


def test_low_reliability_can_trigger_error(monkeypatch):
    ball = engine.simulate_batted_ball(88, 24, -35)
    snap = _make_snap("Left Field", rating=60, reliability=30)
    # Force the error RNG to always trigger
    monkeypatch.setattr(engine, "_rng", SimpleNamespace(random=lambda: 0.0))
    result = engine.resolve_fielding_play(ball, [snap], runner_speed=70)
    assert result.error_type in {"E_FIELD", "E_THROW"}
    assert result.hit_type != "Out"
