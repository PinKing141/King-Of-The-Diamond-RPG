import types

import pytest

from core.io_interface import NoOpIO
from match_engine import controller
from tools import simulation_runner
from world_sim import regional_sim


def test_resolver_silent_injects_noop_io_and_emits_no_stdout(capsys, monkeypatch):
    call_state = {}

    def fake_engine_run_match(*_args, **kwargs):
        call_state["kwargs"] = kwargs
        return "winner"

    monkeypatch.setattr(controller, "run_match", fake_engine_run_match)
    monkeypatch.setattr(controller, "consume_strategy_mods", lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, "_fetch_latest_score", lambda *args, **kwargs: "1 - 0")

    home = types.SimpleNamespace(id=1)
    away = types.SimpleNamespace(id=2)

    class _DummySession:
        def commit(self):
            return None

    session = _DummySession()

    winner, score = controller._simulate_match(
        home,
        away,
        "Practice Match",
        silent=True,
        fast=False,
        persist_results=False,
        session=session,
    )

    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""
    assert call_state["kwargs"].get("io") is not None
    assert winner == "winner"
    assert score == "1 - 0"


def test_simulation_runner_sampling_avoids_func_random(monkeypatch):
    runner = simulation_runner.SimulationRunner(seed=42)

    used_random = False

    def _boom():
        nonlocal used_random
        used_random = True
        raise AssertionError("func.random should not be used for sampling")

    monkeypatch.setattr(simulation_runner.func, "random", _boom)
    monkeypatch.setattr(simulation_runner, "run_ai_skill_progression", lambda *args, **kwargs: [])
    monkeypatch.setattr(simulation_runner.SimulationRunner, "ensure_world", lambda *_: None)
    monkeypatch.setattr(simulation_runner.SimulationRunner, "collect_skill_snapshot", lambda *_: simulation_runner.SkillSnapshot(0, 0, 0.0, 0.0, 0, simulation_runner.Counter()))

    class _FakeQuery:
        def __init__(self, total, ids):
            self._total = total
            self._ids = ids
            self._offset = 0

        def scalar(self):
            return self._total

        def all(self):
            return [types.SimpleNamespace(id=i) for i in self._ids]

        def first(self):
            return types.SimpleNamespace(id=self._ids[self._offset]) if self._offset < len(self._ids) else None

        def count(self):
            return self._total

        def order_by(self, *_args, **_kwargs):
            return self

        def offset(self, n):
            self._offset = n
            return self

        def limit(self, _n):
            return self

    class _FakeSession:
        def __init__(self, ids):
            self.ids = ids

        def query(self, model):
            # func.count(...) passes in a column; School.id passes model itself here
            if getattr(model, "__name__", None) == "School":
                return _FakeQuery(len(self.ids), self.ids)
            return _FakeQuery(len(self.ids), self.ids)

    class _Scope:
        def __init__(self, session):
            self.session = session

        def __enter__(self):
            return self.session

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_ids = list(range(5))
    monkeypatch.setattr(simulation_runner, "session_scope", lambda: _Scope(_FakeSession(fake_ids)))

    runner.simulate_training_seasons(seasons=1, cycles_per_season=0, school_sample=3)
    assert not used_random


def test_regional_strength_cache_limits_calculations(monkeypatch):
    calls = {}

    def fake_calc(_session, sid, **_kwargs):
        calls[sid] = calls.get(sid, 0) + 1
        return 10

    monkeypatch.setattr(regional_sim, "calculate_team_strength", fake_calc)
    monkeypatch.setattr(regional_sim, "quick_resolve_match", lambda session, home, away, **_kwargs: (home, "1-0", False))

    class _FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def yield_per(self, _n):
            return self.rows

    class _FakeSession:
        def __init__(self, rows):
            self.rows = rows

        def query(self, *_args, **_kwargs):
            return _FakeQuery(self.rows)

    schools = [
        types.SimpleNamespace(id=1, name="A", prefecture="Tokyo", prestige=1),
        types.SimpleNamespace(id=2, name="B", prefecture="Tokyo", prestige=1),
        types.SimpleNamespace(id=3, name="C", prefecture="Tokyo", prestige=1),
    ]

    session = _FakeSession(schools)

    winners = regional_sim.run_autumn_regionals(
        session,
        user_school_id=999,
        allow_user_control=False,
        verbose=False,
        io=NoOpIO(),
    )

    assert winners
    assert sum(calls.values()) == len(schools), "strength should be calculated once per school via cache"