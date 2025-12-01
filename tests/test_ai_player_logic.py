"""Tests for the AI skill progression loop."""

from database.setup_db import SessionLocal, Player, PlayerSkill, School
from game import ai_player_logic


def _cleanup(session, player_id, school_id):
    session.query(PlayerSkill).filter(PlayerSkill.player_id == player_id).delete()
    session.query(Player).filter(Player.id == player_id).delete()
    session.query(School).filter(School.id == school_id).delete()
    session.commit()


def test_ai_progression_unlocks_skill_for_npc_school():
    session = SessionLocal()
    school = School(name="AI Elite", prefecture="Test", prestige=95)
    session.add(school)
    session.commit()

    pitcher = Player(
        name="Boss Ace",
        position="Pitcher",
        school_id=school.id,
        control=92,
        volatility=20,
        velocity=152,
        movement=85,
        stamina=90,
        year=3,
    )
    session.add(pitcher)
    session.commit()

    original_should = ai_player_logic._should_attempt_unlock
    ai_player_logic._should_attempt_unlock = lambda p, prest: True
    try:
        unlocks = ai_player_logic.run_ai_skill_progression(
            session,
            prestige_floor=0,
            max_unlocks_per_school=5,
            cycle_label="test",
            school_ids=[school.id],
        )
        assert any(record.player_id == pitcher.id for record in unlocks)
    finally:
        ai_player_logic._should_attempt_unlock = original_should
        _cleanup(session, pitcher.id, school.id)
        session.close()
