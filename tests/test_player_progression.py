"""Tests for milestone-based skill unlocks."""

from database import setup_db
from database.setup_db import (
    Game,
    Player,
    PlayerMilestone,
    PlayerGameStats,
    PlayerSkill,
    School,
    SessionLocal,
)
from game.player_progression import fetch_player_milestone_tags, process_milestone_unlocks


setup_db.ensure_player_skill_schema()
setup_db.ensure_player_milestone_schema()


class _FixedRNG:
    def __init__(self, value: float):
        self.value = value

    def random(self) -> float:
        return self.value


def _cleanup(session, player_id, school_ids, game_ids):
    session.query(PlayerSkill).filter(PlayerSkill.player_id == player_id).delete()
    session.query(PlayerMilestone).filter(PlayerMilestone.player_id == player_id).delete()
    session.query(PlayerGameStats).filter(PlayerGameStats.player_id == player_id).delete()
    for game_id in game_ids:
        session.query(Game).filter(Game.id == game_id).delete()
    session.query(Player).filter(Player.id == player_id).delete()
    for sid in school_ids:
        session.query(School).filter(School.id == sid).delete()
    session.commit()


def test_slugfest_milestone_unlocks_power_surge():
    session = SessionLocal()
    school = School(name="Slugfest High", prefecture="Test", prestige=80)
    opponent = School(name="Rival", prefecture="Test", prestige=20)
    session.add_all([school, opponent])
    session.commit()

    player = Player(name="Cleanup Hero", position="Outfielder", school_id=school.id)
    session.add(player)
    session.commit()

    games = []
    for idx in range(6):
        game = Game(
            home_school_id=school.id,
            away_school_id=opponent.id,
            season_year=2030,
            is_completed=True,
        )
        session.add(game)
        session.commit()
        games.append(game)

        stats_kwargs = {
            "game_id": game.id,
            "player_id": player.id,
            "team_id": school.id,
            "at_bats": 4,
            "hits_batted": 1,
            "homeruns": 0,
            "rbi": 0,
        }
        if idx == 0:
            stats_kwargs.update({"hits_batted": 3, "homeruns": 3, "rbi": 7})
        session.add(PlayerGameStats(**stats_kwargs))
        session.commit()

    try:
        unlocks = process_milestone_unlocks(
            session,
            player,
            season_year=2030,
            rng=_FixedRNG(0.0),
        )
        assert any(entry.skill_key == "power_surge" for entry in unlocks)

        db_count = (
            session.query(PlayerSkill)
            .filter(PlayerSkill.player_id == player.id, PlayerSkill.skill_key == "power_surge")
            .count()
        )
        assert db_count == 1

        milestone_row = (
            session.query(PlayerMilestone)
            .filter(
                PlayerMilestone.player_id == player.id,
                PlayerMilestone.milestone_key == "slugfest_hat_trick",
            )
            .one_or_none()
        )
        assert milestone_row is not None
        assert milestone_row.skill_key == "power_surge"
    finally:
        _cleanup(session, player.id, [school.id, opponent.id], [g.id for g in games])
        session.close()


def test_pitcher_milestone_respects_season_filter():
    session = SessionLocal()
    school = School(name="Ace Factory", prefecture="Test", prestige=90)
    opponent = School(name="Challenger", prefecture="Test", prestige=15)
    session.add_all([school, opponent])
    session.commit()

    pitcher = Player(name="Strikeout King", position="Pitcher", school_id=school.id)
    session.add(pitcher)
    session.commit()

    # Older season performance should be ignored when a different year is evaluated.
    old_game = Game(
        home_school_id=school.id,
        away_school_id=opponent.id,
        season_year=2029,
        is_completed=True,
    )
    new_game = Game(
        home_school_id=opponent.id,
        away_school_id=school.id,
        season_year=2030,
        is_completed=True,
    )
    extra_games = [
        Game(
            home_school_id=school.id,
            away_school_id=opponent.id,
            season_year=2030,
            is_completed=True,
        )
        for _ in range(3)
    ]
    session.add_all([old_game, new_game, *extra_games])
    session.commit()

    session.add_all(
        [
            PlayerGameStats(
                game_id=old_game.id,
                player_id=pitcher.id,
                team_id=school.id,
                strikeouts_pitched=14,
                innings_pitched=7.0,
            ),
            PlayerGameStats(
                game_id=new_game.id,
                player_id=pitcher.id,
                team_id=school.id,
                strikeouts_pitched=13,
                innings_pitched=6.0,
            ),
        ]
    )
    for filler in extra_games:
        session.add(
            PlayerGameStats(
                game_id=filler.id,
                player_id=pitcher.id,
                team_id=school.id,
                strikeouts_pitched=0,
                innings_pitched=5.0,
            )
        )
    session.commit()

    try:
        none_unlocked = process_milestone_unlocks(
            session,
            pitcher,
            season_year=2028,
            rng=_FixedRNG(0.0),
        )
        assert none_unlocked == []

        unlocks = process_milestone_unlocks(
            session,
            pitcher,
            season_year=2030,
            rng=_FixedRNG(0.0),
        )
        assert any(entry.skill_key == "strikeout_artist" for entry in unlocks)

        count = (
            session.query(PlayerSkill)
            .filter(PlayerSkill.player_id == pitcher.id, PlayerSkill.skill_key == "strikeout_artist")
            .count()
        )
        assert count == 1

        tag_map = fetch_player_milestone_tags(session, [pitcher.id])
        assert pitcher.id in tag_map
        keys = {entry["key"] for entry in tag_map[pitcher.id]}
        assert "strikeout_showcase" in keys
    finally:
        cleanup_games = [old_game.id, new_game.id, *[g.id for g in extra_games]]
        _cleanup(session, pitcher.id, [school.id, opponent.id], cleanup_games)
        session.close()


def test_fetch_tags_ignores_empty_ids():
    session = SessionLocal()
    try:
        assert fetch_player_milestone_tags(session, []) == {}
        assert fetch_player_milestone_tags(session, [None, 0]) == {}
    finally:
        session.close()
