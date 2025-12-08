import math
import random

from database.setup_db import GameState, Player, School, SessionLocal
from core.game_context import GameContext
from core.services import SessionProvider
from game.loop.weekly_scheduler import execute_schedule_silent


def _make_context(session):
    provider = SessionProvider(lambda: session)
    return GameContext(session_factory=lambda: session, session_provider=provider)


def test_execute_schedule_uses_dto_repos_and_updates_fatigue():
    session = SessionLocal()
    school = School(name="DTO High", prefecture="Test", prestige=40)
    session.add(school)
    session.commit()

    player = Player(name="DTO User", position="Pitcher", school_id=school.id, fatigue=30)
    session.add(player)
    session.commit()

    state = GameState(current_day="MON", current_week=1, current_month=4, current_year=2024, active_player_id=player.id)
    session.add(state)
    session.commit()

    ctx = _make_context(session)
    ctx.set_player(player.id, player.school_id)

    # Minimal schedule: single rest slot to avoid match flows
    schedule_grid = [[None for _ in range(3)] for _ in range(7)]
    schedule_grid[0][0] = "rest"

    try:
        execution, summary = execute_schedule_silent(ctx, schedule_grid, current_week=1, rng_seed=123)
        session.refresh(player)
        assert execution.results, "No slot results returned"
        # Rest should not increase fatigue; expect drop from 30
        assert player.fatigue <= 30
        # Summary should reflect at least one slot
        assert summary.stat_gains is not None
    finally:
        session.delete(state)
        session.delete(player)
        session.delete(school)
        session.commit()
        session.close()


def test_execute_schedule_training_slot_deterministic_with_seed():
    session = SessionLocal()
    school = School(name="Seeded High", prefecture="Test", prestige=40)
    session.add(school)
    session.commit()

    player = Player(name="Seeded User", position="Pitcher", school_id=school.id, fatigue=0, control=40)
    session.add(player)
    session.commit()

    state = GameState(current_day="MON", current_week=1, current_month=4, current_year=2024, active_player_id=player.id)
    session.add(state)
    session.commit()

    ctx = _make_context(session)
    ctx.set_player(player.id, player.school_id)

    schedule_grid = [[None for _ in range(3)] for _ in range(7)]
    schedule_grid[0][0] = "train_control"

    seed = 777
    expected_variance = random.Random(seed).uniform(0.9, 1.1)

    try:
        execution, _summary = execute_schedule_silent(ctx, schedule_grid, current_week=1, rng_seed=seed)
        slot = execution.results[0]
        xp_gain = slot.training_details.get("xp_gains", {}).get("control")
        assert xp_gain is not None
        assert math.isclose(xp_gain, expected_variance, rel_tol=1e-6)
        session.refresh(player)
        assert player.fatigue == 10  # drill_generic cost
    finally:
        session.delete(state)
        session.delete(player)
        session.delete(school)
        session.commit()
        session.close()
