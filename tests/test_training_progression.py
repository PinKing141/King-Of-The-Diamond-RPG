import json
from unittest.mock import patch

from database.setup_db import Player, School, SessionLocal
from game.game_context import GameContext
from game import training_logic


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
    player.training_xp = json.dumps({"control": threshold - 0.2})
    session.add(player)
    session.commit()

    ctx = _make_context(session, player)
    try:
        with patch("game.training_logic.check_injury_risk", return_value=(False, None)):
            with patch("game.training_logic.random.uniform", return_value=1.0), patch(
                "game.training_logic.random.random", return_value=1.0
            ):
                result = training_logic.apply_scheduled_action(ctx, "train_control", commit=False)
        session.refresh(player)
        assert result["stat_changes"].get("control") == 1
        assert result["xp_gains"].get("control") == 1.0
        assert player.control >= 46
        pool = json.loads(player.training_xp)
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
    player.training_xp = json.dumps({"power": 1.5})
    session.add(player)
    session.commit()

    ctx = _make_context(session, player)
    try:
        with patch("game.training_logic.check_injury_risk", return_value=(False, None)):
            with patch("game.training_logic.random.uniform", return_value=1.0), patch(
                "game.training_logic.random.random", return_value=0.0
            ):
                result = training_logic.apply_scheduled_action(ctx, "train_power", commit=False)
        session.refresh(player)
        breakthrough = result.get("breakthrough")
        assert breakthrough is not None
        assert breakthrough["stat"] == "power"
        xp_bucket = json.loads(player.training_xp)
        assert xp_bucket.get("power", 0) == 0
        assert player.power >= 53
    finally:
        _cleanup(session, player, school)
