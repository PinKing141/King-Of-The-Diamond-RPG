from __future__ import annotations

from types import SimpleNamespace

from core.event_bus import EventBus


class DummyMomentumSystem:
    def get_multiplier(self, team_id):  # pragma: no cover - simple stub
        return 1.0


def make_player(player_id: int, name: str, position: str, **overrides):
    defaults = {
        "id": player_id,
        "name": name,
        "last_name": name,
        "position": position,
        "team_id": overrides.get("team_id"),
        "school_id": overrides.get("school_id", overrides.get("team_id", 1)),
        "is_starter": overrides.get("is_starter", True),
        "role": overrides.get("role", "starter"),
        "velocity": overrides.get("velocity", 140),
        "control": overrides.get("control", 55),
        "movement": overrides.get("movement", 50),
        "trust_baseline": overrides.get("trust_baseline", 55),
        "contact": overrides.get("contact", 60),
        "power": overrides.get("power", 60),
        "discipline": overrides.get("discipline", 55),
        "eye": overrides.get("eye", 55),
        "speed": overrides.get("speed", 55),
        "drive": overrides.get("drive", 55),
        "loyalty": overrides.get("loyalty", 55),
        "volatility": overrides.get("volatility", 45),
        "morale": overrides.get("morale", 60),
        "slump_timer": overrides.get("slump_timer", 0),
        "arm_slot": overrides.get("arm_slot", "Three-Quarters"),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_team(team_id: int, name: str):
    return SimpleNamespace(id=team_id, name=name, school_name=name)


def make_basic_match_state():
    from match_engine.pregame import MatchState

    home_team = make_team(1, "Seidou")
    away_team = make_team(2, "Inashiro")

    home_lineup = [make_player(i + 1, f"Home{i+1}", "Catcher" if i == 0 else "CF", team_id=home_team.id) for i in range(9)]
    away_lineup = [make_player(i + 101, f"Away{i+1}", "Catcher" if i == 0 else "CF", team_id=away_team.id) for i in range(9)]

    home_pitcher = make_player(201, "AceHome", "Pitcher", team_id=home_team.id)
    away_pitcher = make_player(202, "AceAway", "Pitcher", team_id=away_team.id)

    state = MatchState(
        home_team,
        away_team,
        home_lineup,
        away_lineup,
        home_pitcher,
        away_pitcher,
        db_session=None,
        event_bus=EventBus(),
    )
    return state
