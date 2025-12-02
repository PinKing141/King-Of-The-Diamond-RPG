"""Tests for the skill acquisition helper."""

from database import setup_db
from database.setup_db import SessionLocal, Player, PlayerSkill
from game.skill_system import (
    check_and_grant_skills,
    player_has_skill,
    grant_skill_by_key,
    remove_skill_by_key,
    sync_player_skills,
    list_player_skill_keys,
)

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
        assert "Speed Demon" not in initial_unlocks
        assert not player_has_skill(player, "speed_demon")

        player.speed = 62
        session.add(player)
        session.commit()

        unlocked = check_and_grant_skills(session, player)
        assert "Speed Demon" in unlocked
        assert player_has_skill(player, "speed_demon")
    finally:
        _cleanup_player(session, player.id)
        session.close()


def test_remove_skill_by_key_clears_cache_and_db():
    session = SessionLocal()
    player = Player(
        name="Closer",
        position="Pitcher",
        year=2,
    )
    session.add(player)
    session.commit()

    try:
        grant_skill_by_key(session, player, "shutdown_closer")
        assert player_has_skill(player, "shutdown_closer")
        assert remove_skill_by_key(session, player, "shutdown_closer")
        assert not player_has_skill(player, "shutdown_closer")
        remaining = (
            session.query(PlayerSkill)
            .filter_by(player_id=player.id, skill_key="shutdown_closer")
            .count()
        )
        assert remaining == 0
    finally:
        _cleanup_player(session, player.id)
        session.close()


def test_sync_player_skills_prunes_unknown_and_duplicates():
    session = SessionLocal()
    player = Player(
        name="Legacy",
        position="Pitcher",
        year=3,
    )
    session.add(player)
    session.commit()

    try:
        # Manually insert duplicate + unknown traits to emulate legacy saves.
        session.add(PlayerSkill(player_id=player.id, skill_key="clutch_hitter"))
        session.add(PlayerSkill(player_id=player.id, skill_key="CLUTCH_HITTER"))
        session.add(PlayerSkill(player_id=player.id, skill_key="unknown_trait"))
        session.commit()

        stats = sync_player_skills(session)
        session.commit()

        assert stats["duplicate_entries_pruned"] == 1
        assert stats["unknown_entries_pruned"] == 1

        session.refresh(player)
        remaining_keys = list_player_skill_keys(player)
        assert remaining_keys == ["clutch_hitter"]
    finally:
        _cleanup_player(session, player.id)
        session.close()
