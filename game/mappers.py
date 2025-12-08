from __future__ import annotations

from typing import Any

from database.setup_db import Player, Team
from game.dto import PlayerDTO, TeamDTO


TRAINING_STAT_KEYS = {
    "control",
    "velocity",
    "stamina",
    "movement",
    "power",
    "contact",
    "speed",
    "fielding",
    "throwing",
    "command",
}


def player_to_dto(model: Player) -> PlayerDTO:
    stats = {key: getattr(model, key, 0) or 0 for key in TRAINING_STAT_KEYS}
    return PlayerDTO(
        id=model.id,
        school_id=getattr(model, "school_id", None),
        fatigue=getattr(model, "fatigue", 0) or 0,
        growth_tag=getattr(model, "growth_tag", None),
        conditioning=getattr(model, "conditioning", 50) or 50,
        injury_days=getattr(model, "injury_days", 0) or 0,
        jersey_number=getattr(model, "jersey_number", None),
        position=getattr(model, "position", None),
        slump_timer=getattr(model, "slump_timer", 0) or 0,
        stats=stats,
    )


def apply_training_result(model: Player, result: dict) -> None:
    stat_changes = result.get("stat_changes") or {}
    xp_gains = result.get("xp_gains") or {}
    new_fatigue = result.get("new_fatigue")

    for stat, delta in stat_changes.items():
        current = getattr(model, stat, 0) or 0
        setattr(model, stat, current + delta)
    for stat, delta in xp_gains.items():
        if stat in TRAINING_STAT_KEYS:
            current = getattr(model, stat, 0) or 0
            setattr(model, stat, current + delta)
    if new_fatigue is not None:
        model.fatigue = new_fatigue


def team_to_dto(model: Team) -> TeamDTO:
    return TeamDTO(
        id=model.id,
        name=getattr(model, "name", "Unknown"),
        prestige=getattr(model, "prestige", 0) or 0,
        era_label=getattr(model, "current_era", None),
        era_momentum=getattr(model, "era_momentum", 0) or 0,
    )
