from __future__ import annotations

import json
from typing import Any

from database.setup_db import Game, GameState, Performance, ensure_game_schema
from game.personnel.personality_effects import evaluate_postgame_slumps
from game.personnel.relationship_manager import apply_confidence_relationships
from .confidence import get_confidence_summary


class MatchPersistenceService:
    """Persists match outcomes and player stats to the database."""

    @staticmethod
    def save_game_results(state: Any) -> None:
        ensure_game_schema()
        weather = getattr(state, "weather", None)
        umpire = getattr(state, "umpire", None)
        tilt = getattr(state, "umpire_call_tilt", {}) or {}
        home_id = getattr(state.home_team, "id", None)
        away_id = getattr(state.away_team, "id", None)
        home_tilt = tilt.get(home_id, {"favored": 0, "squeezed": 0})
        away_tilt = tilt.get(away_id, {"favored": 0, "squeezed": 0})
        error_summary = getattr(state, "error_summary", None)
        game_row = Game(
            season_year=1,
            tournament="Season Match",
            home_school_id=state.home_team.id,
            away_school_id=state.away_team.id,
            home_score=state.home_score,
            away_score=state.away_score,
            is_completed=True,
            weather_label=getattr(weather, "label", None),
            weather_condition=getattr(weather, "condition", None),
            weather_precip=getattr(weather, "precipitation", None),
            weather_temperature_f=getattr(weather, "temperature_f", None),
            weather_wind_speed=getattr(weather, "wind_speed_mph", None),
            weather_wind_direction=getattr(weather, "wind_direction", None),
            weather_summary=weather.describe() if weather else None,
            umpire_name=getattr(umpire, "name", None),
            umpire_description=getattr(umpire, "description", None),
            umpire_zone_bias=getattr(umpire, "zone_bias", None),
            umpire_home_bias=getattr(umpire, "home_bias", None),
            umpire_temperament=getattr(umpire, "temperament", None),
            umpire_favored_home=home_tilt.get("favored", 0),
            umpire_squeezed_home=home_tilt.get("squeezed", 0),
            umpire_favored_away=away_tilt.get("favored", 0),
            umpire_squeezed_away=away_tilt.get("squeezed", 0),
            error_summary=json.dumps(error_summary) if error_summary is not None else None,
            rivalry_summary=json.dumps(getattr(state, "rival_postgame", None))
            if getattr(state, "rival_postgame", None)
            else None,
        )
        db_session = state.db_session
        if db_session is None:
            raise ValueError("MatchState missing db_session for persistence.")

        db_session.add(game_row)
        db_session.flush()

        gamestate_row = db_session.query(GameState).first()
        if gamestate_row is not None:
            gamestate_row.last_error_summary = json.dumps(error_summary) if error_summary is not None else None
            db_session.add(gamestate_row)

        for player_id, stat in state.stats.items():
            team_id = state.player_team_map.get(player_id)
            if team_id is None:
                is_home = any(p.id == player_id for p in state.home_roster if p) or getattr(state.home_pitcher, "id", None) == player_id
                team_id = state.home_team.id if is_home else state.away_team.id

            perf = Performance(
                game_id=game_row.id,
                player_id=player_id,
                team_id=team_id,
                at_bats=stat["at_bats"],
                hits=stat["hits"],
                homeruns=stat["homeruns"],
                rbi=stat["rbi"],
                strikeouts=stat["strikeouts"],
                walks=stat["walks"],
                innings_pitched=stat["innings_pitched"],
                strikeouts_pitched=stat["strikeouts_pitched"],
                runs_allowed=stat["runs_allowed"],
                confidence=state.confidence_map.get(player_id, 0),
            )
            db_session.add(perf)

        state.confidence_summary_snapshot = get_confidence_summary(state)
        apply_confidence_relationships(db_session, state.confidence_summary_snapshot)
        evaluate_postgame_slumps(state)
        db_session.commit()


__all__ = ["MatchPersistenceService"]
