from unittest.mock import patch

from database.setup_db import Player, PlayerXP, School, SessionLocal
from core.game_context import GameContext
from game import training_logic
from game.services.training_service import TrainingService


class DummyRNG:
    def __init__(self, *, random_values=None, uniform_value=1.0):
        self.random_values = list(random_values or [])
        self.uniform_value = uniform_value

    def random(self):
        if self.random_values:
            return self.random_values.pop(0)
        return 1.0

    def uniform(self, _a, _b):
        return self.uniform_value


def _make_context(session, player):
    ctx = GameContext(lambda: session)
    ctx.set_player(player.id, player.school_id)
    return ctx


def _cleanup(session, *models):
    for model in models:
        session.delete(model)
    session.commit()
    session.close()


def test_training_xp_levels_stat_after_threshold():
    session = SessionLocal()
    school = School(name="XP High", prefecture="Test", prestige=40)
    session.add(school)
    session.commit()

    player = Player(name="Grinder", position="Pitcher", school_id=school.id, control=45, determination=60)
    threshold = training_logic._xp_threshold(player.control)
    player.xp_entries.append(PlayerXP(stat_key="control", xp=threshold - 0.2))
    session.add(player)
    session.commit()

    ctx = _make_context(session, player)
    try:
        service = TrainingService(rng=DummyRNG(uniform_value=1.0, random_values=[1.0]))
        with patch("game.training_logic.check_injury_risk", return_value=(False, None)):
            result = service.apply_action(ctx, "train_control", commit=False)
        session.refresh(player)
        assert result["stat_changes"].get("control") == 1
        assert result["xp_gains"].get("control") == 1.0
        assert player.control >= 46
        pool = {entry.stat_key: entry.xp for entry in player.xp_entries}
        assert pool.get("control", 0) < training_logic._xp_threshold(player.control)
    finally:
        _cleanup(session, player, school)


def test_breakthrough_resets_xp_bucket():
    session = SessionLocal()
    school = School(name="Inspiration", prefecture="Test", prestige=55)
    session.add(school)
    session.commit()

    player = Player(
        name="Spark",
        position="Pitcher",
        school_id=school.id,
        power=52,
        determination=95,
    )
    player.xp_entries.append(PlayerXP(stat_key="power", xp=1.5))
    session.add(player)
    session.commit()

    ctx = _make_context(session, player)
    try:
        service = TrainingService(rng=DummyRNG(uniform_value=1.0, random_values=[0.0]))
        with patch("game.training_logic.check_injury_risk", return_value=(False, None)):
            result = service.apply_action(ctx, "train_power", commit=False)
        session.refresh(player)
        breakthrough = result.get("breakthrough")
        assert breakthrough is not None
        assert breakthrough["stat"] == "power"
        xp_bucket = {entry.stat_key: entry.xp for entry in player.xp_entries}
        assert xp_bucket.get("power", 0) == 0
        assert player.power >= 53
    finally:
        _cleanup(session, player, school)
