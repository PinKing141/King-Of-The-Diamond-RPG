import json

from database.setup_db import GameState, Player, School, SessionLocal
from game.weekly_scheduler import CoachOrder, _record_coach_order_result


def test_record_coach_order_result_serializes_payload():
    session = SessionLocal()
    school = School(name="Test Prep", prefecture="Test", prestige=10)
    session.add(school)
    session.commit()

    player = Player(
        name="Rookie",
        position="Pitcher",
        school_id=school.id,
        year=1,
        jersey_number=18,
    )
    session.add(player)
    session.commit()

    gamestate = session.query(GameState).first()
    if gamestate is None:
        gamestate = GameState(
            current_day="MON",
            current_week=1,
            current_month=4,
            current_year=2024,
        )
        session.add(gamestate)
        session.commit()

    original_payload = gamestate.last_coach_order_result
    try:
        order = CoachOrder(
            key="test_order",
            description="Complete two bullpen days",
            requirement={"type": "action_count", "actions": ["train_control"], "count": 2},
            reward_trust=4,
            reward_ability_points=1,
        )
        progress = {"progress": 2, "target": 2, "completed": 1}
        reward_delta = {"trust": 4, "ability_points": 1}

        _record_coach_order_result(
            session,
            current_week=7,
            player=player,
            coach_order=order,
            order_progress=progress,
            reward_delta=reward_delta,
        )
        session.commit()
        session.refresh(gamestate)

        payload = json.loads(gamestate.last_coach_order_result)
        assert payload["week"] == 7
        assert payload["player"]["id"] == player.id
        assert payload["order"]["key"] == "test_order"
        assert payload["progress"]["value"] == 2
        assert payload["completed"] is True
        assert payload["reward_delta"]["ability_points"] == 1
    finally:
        gamestate.last_coach_order_result = original_payload
        session.add(gamestate)
        session.query(Player).filter(Player.id == player.id).delete()
        session.query(School).filter(School.id == school.id).delete()
        session.commit()
        session.close()
