from types import SimpleNamespace

from core.event_bus import EventBus
from match_engine import batter_logic, base_running
from match_engine.states import EventType
from world_sim.baserunning import PickoffOutcome, RunnerThreatState, SlideStepResult


def _make_state_with_runner():
    runner = SimpleNamespace(id=99, speed=80, awareness=65)
    return SimpleNamespace(
        runners=[runner, None, None],
        event_bus=EventBus(),
        crowd_intensity=4.0,
    )


def test_capture_runner_threats_emits_baserun_events():
    state = _make_state_with_runner()
    received = []
    state.event_bus.subscribe(EventType.BASERUN_THREAT.value, received.append)

    threats = batter_logic._capture_runner_threats(state)

    assert 0 in threats
    assert state._cached_runner_threats[0] is threats[0]
    assert received, "threat snapshots should publish to the bus"
    assert received[0]["runner_id"] == 99
    assert received[0]["base"] == 0


def test_resolve_steal_attempt_bridges_to_world_helper(monkeypatch):
    runner = SimpleNamespace(id=7)
    state = SimpleNamespace(runners=[runner, None, None])
    fake_threat = SimpleNamespace(runner=runner, base_index=0)
    pitcher = SimpleNamespace(control=60)
    catcher = SimpleNamespace(throwing=65)

    monkeypatch.setattr(base_running, "prepare_runner_state", lambda *_: fake_threat)

    called = {}

    def _fake_resolve(state_arg, *, threat, pitcher, catcher, delivery_time=None, pop_time=None):
        called["state"] = state_arg
        called["threat"] = threat
        called["pitcher_id"] = getattr(pitcher, "id", None)
        return SimpleNamespace(success=True, description="SAFE")

    monkeypatch.setattr(base_running, "resolve_threat_steal", _fake_resolve)

    success, desc = base_running.resolve_steal_attempt(state, runner, pitcher, catcher, "2B")

    assert success is True
    assert desc == "SAFE"
    assert called["state"] is state
    assert called["threat"] is fake_threat


def test_resolve_steal_attempt_handles_missing_runner():
    state = SimpleNamespace(runners=[None, None, None])
    pitcher = SimpleNamespace(control=50)
    catcher = SimpleNamespace(throwing=50)

    success, desc = base_running.resolve_steal_attempt(state, None, pitcher, catcher, "2B")

    assert success is False
    assert desc == "No runner to steal."


def test_maybe_call_squeeze_play_triggers_in_late_game(monkeypatch):
    batter = SimpleNamespace(id=5, contact=70)
    runner_third = SimpleNamespace(id=9, speed=75)
    runners = [SimpleNamespace(id=2, speed=60), None, runner_third]
    coach = SimpleNamespace(volatility=65, drive=70, loyalty=45)
    state = SimpleNamespace(
        inning=8,
        outs=0,
        top_bottom="Top",
        runners=runners,
        pressure_index=7.0,
        away_score=1,
        home_score=1,
        defensive_shift="normal",
        away_team=SimpleNamespace(id=2, name="Away", coach=coach),
        home_team=SimpleNamespace(id=1, name="Home", coach=None),
    )
    runner_threats = {2: SimpleNamespace(lead_off_distance=8.5, jump_quality=1.2, pressure=0.0)}
    rolls = iter([0.0, 0.4])

    def _fake_random():
        return next(rolls)

    monkeypatch.setattr(batter_logic.rng, "random", _fake_random)
    monkeypatch.setattr(batter_logic.rng, "uniform", lambda a, b: 0.0)

    intent = batter_logic._maybe_call_squeeze_play(state, batter, runner_threats)

    assert intent is not None
    assert intent.squeeze is True


def test_resolve_bunt_contact_returns_runner_advances(monkeypatch):
    runner_third = SimpleNamespace(id=3, speed=80)
    runners = [SimpleNamespace(id=1), None, runner_third]
    state = SimpleNamespace(runners=runners, pressure_index=6.0, outs=0)
    batter = SimpleNamespace(id=7, contact=65)
    pitcher = SimpleNamespace(control=60)
    intent = batter_logic.BuntIntent(play="squeeze", runner_base=2, target_side="first", squeeze=True)
    rolls = iter([0.0, 0.99])

    def _fake_random():
        return next(rolls)

    monkeypatch.setattr(batter_logic.rng, "random", _fake_random)

    result = batter_logic._resolve_bunt_contact(state, batter, pitcher, intent, {})

    assert result.special_play == "squeeze"
    assert result.runner_advances[0][1] == 3
    assert result.sacrifice is True
    assert result.rbi_credit is True


def test_apply_runner_advancements_scores_and_clears():
    runner_third = SimpleNamespace(id=4)
    state = SimpleNamespace(runners=[None, None, runner_third])

    runs = batter_logic._apply_runner_advancements(state, [(2, 3, runner_third)])

    assert runs == 1
    assert state.runners[2] is None


def test_apply_slide_step_modifiers_applies_penalties(monkeypatch):
    pitcher = SimpleNamespace(id=77, control=70, velocity=140, stamina=90)
    state = SimpleNamespace(pitch_counts={77: 95}, _pending_delivery_time=None)
    threat = RunnerThreatState(
        runner=SimpleNamespace(id=3, name="Speedy"),
        base_index=0,
        lead_off_distance=8.0,
        jump_quality=1.2,
        runner_speed_time=3.4,
        pressure=0.0,
    )
    runner_threats = {0: threat}

    def fake_eval(pitcher_obj, *, use_slide_step, fatigue_level):
        if use_slide_step:
            return SlideStepResult(True, 1.25, 5.0, 3.5, 1.2)
        return SlideStepResult(False, 1.45, 0.0, 0.0, 0.1)

    monkeypatch.setattr(batter_logic, "evaluate_slide_step", fake_eval)
    monkeypatch.setattr(batter_logic, "_should_slide_step", lambda *args, **kwargs: True)

    mods = {}
    result = batter_logic._apply_slide_step_modifiers(state, pitcher, mods, runner_threats)

    assert result.used_slide_step is True
    assert state._pending_delivery_time == 1.25
    assert mods["control"] == -5.0
    assert mods["velocity"] == -3.5


def test_pickoff_attempt_records_out(monkeypatch):
    runner = SimpleNamespace(id=9, name="Quick")
    threat = RunnerThreatState(
        runner=runner,
        base_index=0,
        lead_off_distance=8.5,
        jump_quality=1.0,
        runner_speed_time=3.4,
        pressure=0.0,
    )
    state = SimpleNamespace(
        runners=[runner, None, None],
        outs=0,
        pressure_index=7.0,
        _cached_runner_threats={0: threat},
        pitch_counts={42: 80},
    )
    pitcher = SimpleNamespace(id=42, name="Ace", pickoff_rating=70, control=65, stamina=90)

    monkeypatch.setattr(batter_logic.rng, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(batter_logic.rng, "random", lambda: 0.0)

    def fake_pickoff(state_obj, *, threat, pitcher):
        return PickoffOutcome(True, True, 1.0, -1.0, "Picked!")

    monkeypatch.setattr(batter_logic, "simulate_pickoff", fake_pickoff)

    assert batter_logic._maybe_call_pickoff_attempt(state, pitcher, {0: threat}) is True
    assert state.runners[0] is None
    assert state.outs == 1


def test_pickoff_attempt_handles_safe_runner(monkeypatch):
    runner = SimpleNamespace(id=10, name="Safe")
    threat = RunnerThreatState(
        runner=runner,
        base_index=0,
        lead_off_distance=7.2,
        jump_quality=0.4,
        runner_speed_time=3.6,
        pressure=0.0,
    )
    state = SimpleNamespace(
        runners=[runner, None, None],
        outs=0,
        pressure_index=5.0,
        _cached_runner_threats={0: threat},
        pitch_counts={42: 50},
    )
    pitcher = SimpleNamespace(id=42, name="Calm", pickoff_rating=60, control=60, stamina=95)

    monkeypatch.setattr(batter_logic.rng, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(batter_logic.rng, "random", lambda: 0.0)

    def fake_pickoff(state_obj, *, threat, pitcher):
        threat.adjust_lead(-0.5)
        return PickoffOutcome(True, False, 0.5, -0.5, "Back safely")

    monkeypatch.setattr(batter_logic, "simulate_pickoff", fake_pickoff)

    assert batter_logic._maybe_call_pickoff_attempt(state, pitcher, {0: threat}) is False
    assert state.runners[0] is runner
    assert state.outs == 0
