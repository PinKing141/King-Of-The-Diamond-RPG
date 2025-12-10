from __future__ import annotations

from typing import Iterable

from database.setup_db import Player, PitchRepertoire, PlayerXP, Team
from game.services.dtos import (
    PitchRepertoireDTO,
    PlayerTrainingDTO,
    PlayerXPEntryDTO,
    TeamDTO,
)


def player_to_training_dto(player: Player) -> PlayerTrainingDTO:
    stats = {
        key: float(getattr(player, key, 0) or 0)
        for key in [
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
            "academic_skill",
            "test_score",
        ]
    }
    repertoire_dtos = [
        PitchRepertoireDTO(
            pitch_name=entry.pitch_name,
            mastery_level=getattr(entry, "mastery_level", 0) or 0,
            mastery_xp=getattr(entry, "mastery_xp", 0) or 0,
        )
        for entry in getattr(player, "pitch_repertoire", []) or []
    ]
    xp_entries = [
        PlayerXPEntryDTO(stat_key=entry.stat_key, xp=float(entry.xp or 0))
        for entry in getattr(player, "xp_entries", []) or []
    ]
    return PlayerTrainingDTO(
        id=getattr(player, "id", None),
        school_id=getattr(player, "school_id", None),
        position=getattr(player, "position", None),
        growth_tag=getattr(player, "growth_tag", None),
        conditioning=float(getattr(player, "conditioning", 50) or 50),
        fatigue=int(getattr(player, "fatigue", 0) or 0),
        injury_days=int(getattr(player, "injury_days", 0) or 0),
        jersey_number=getattr(player, "jersey_number", None),
        slump_timer=int(getattr(player, "slump_timer", 0) or 0),
        stats=stats,
        pitch_repertoire=repertoire_dtos,
        xp_entries=xp_entries,
        attributes={
            "role": getattr(player, "role", None),
            "drive": getattr(player, "drive", None),
            "determination": getattr(player, "determination", None),
            "is_two_way": getattr(player, "is_two_way", False),
            "growth_tag": getattr(player, "growth_tag", None),
            "growth_style": getattr(player, "growth_style", None),
            "position": getattr(player, "position", None),
            "slump_timer": getattr(player, "slump_timer", 0),
        },
    )


def apply_training_dto_to_player(player: Player, dto: PlayerTrainingDTO) -> None:
    player.fatigue = dto.fatigue
    player.injury_days = dto.injury_days
    player.jersey_number = dto.jersey_number
    player.slump_timer = dto.slump_timer
    player.conditioning = dto.conditioning
    player.growth_tag = dto.growth_tag
    player.growth_style = dto.attributes.get("growth_style", getattr(player, "growth_style", None))
    player.position = dto.position

    for key, value in dto.stats.items():
        setattr(player, key, value)

    # Replace XP entries
    existing: Iterable[PlayerXP] = getattr(player, "xp_entries", []) or []
    for entry in list(existing):
        try:
            player.xp_entries.remove(entry)
        except ValueError:
            pass
    for xp_entry in dto.xp_entries:
        player.xp_entries.append(PlayerXP(stat_key=xp_entry.stat_key, xp=xp_entry.xp))

    # Replace repertoire if we have source objects
    repertoire: Iterable[PitchRepertoire] = getattr(player, "pitch_repertoire", []) or []
    if repertoire:
        for entry in repertoire:
            try:
                player.pitch_repertoire.remove(entry)
            except ValueError:
                pass
        for dto_entry in dto.pitch_repertoire:
            player.pitch_repertoire.append(
                PitchRepertoire(
                    pitch_name=dto_entry.pitch_name,
                    mastery_level=dto_entry.mastery_level,
                    mastery_xp=dto_entry.mastery_xp,
                )
            )


def team_to_dto(team: Team) -> TeamDTO:
    return TeamDTO(
        id=getattr(team, "id", None),
        name=getattr(team, "name", ""),
        prestige=int(getattr(team, "prestige", 0) or 0),
        era=getattr(team, "current_era", None),
        era_momentum=int(getattr(team, "era_momentum", 0) or 0),
    )
