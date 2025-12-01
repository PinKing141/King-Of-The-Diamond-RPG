"""Tests for the skill acquisition helper."""

from database import setup_db
from database.setup_db import SessionLocal, Player, PlayerSkill
from game.skill_system import check_and_grant_skills, player_has_skill

setup_db.ensure_player_skill_schema()


def _cleanup_player(session, player_id: int):
    session.query(PlayerSkill).filter(PlayerSkill.player_id == player_id).delete()
    session.query(Player).filter(Player.id == player_id).delete()
    session.commit()


def test_control_freak_unlocks_once():
    session = SessionLocal()
    player = Player(
        name="Test Pitcher",
        position="Pitcher",
        control=82,
        volatility=30,
        year=1,
    )
    session.add(player)
    session.commit()

    try:
        unlocked = check_and_grant_skills(session, player)
        assert "Control Freak" in unlocked
        assert player_has_skill(player, "control_freak")

        # Second check should not grant duplicate entries
        unlocked_again = check_and_grant_skills(session, player)
        assert "Control Freak" not in unlocked_again

        db_count = session.query(PlayerSkill).filter_by(player_id=player.id, skill_key="control_freak").count()
        assert db_count == 1
    finally:
        _cleanup_player(session, player.id)
        session.close()


def test_speed_demon_triggers_after_stat_gain():
    session = SessionLocal()
    player = Player(
        name="Speedy",
        position="Outfielder",
        speed=50,
        discipline=60,
        year=1,
    )
    session.add(player)
    session.commit()

    try:
        initial_unlocks = check_and_grant_skills(session, player)
        assert initial_unlocks == []

        player.speed = 62
        session.add(player)
        session.commit()

        unlocked = check_and_grant_skills(session, player)
        assert "Speed Demon" in unlocked
        assert player_has_skill(player, "speed_demon")
    finally:
        _cleanup_player(session, player.id)
        session.close()
