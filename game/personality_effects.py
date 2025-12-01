from __future__ import annotations

import random
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database.setup_db import Player


def _clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))


def adjust_player_morale(player: Player, delta: float) -> None:
    base = getattr(player, "morale", 60) or 60
    player.morale = _clamp(base + delta)


def adjust_team_morale(session: Session, school_id: int, delta: float, exclude_ids: Optional[Iterable[int]] = None) -> None:
    exclude = set(exclude_ids or [])
    players = (
        session.query(Player)
        .filter(Player.school_id == school_id)
        .all()
    )
    for teammate in players:
        if teammate.id in exclude:
            continue
        adjust_player_morale(teammate, delta)
        session.add(teammate)


def flag_player_slump(player: Player, duration: Optional[int] = None) -> None:
    player.slump_timer = max(int(duration or random.randint(2, 4)), 1)
    adjust_player_morale(player, -6)


def decay_slump(player: Player) -> bool:
    timer = getattr(player, "slump_timer", 0) or 0
    if timer <= 0:
        return False
    player.slump_timer = max(0, timer - 1)
    if player.slump_timer == 0:
        adjust_player_morale(player, 4)
        return True
    return False


def evaluate_postgame_slumps(state) -> None:
    """Review match stats and assign slump timers to low-drive players after bad games."""
    session = state.db_session
    if session is None:
        return

    player_map = {}
    for roster in (state.home_lineup + state.away_lineup):
        player_map[roster.id] = roster
    for pitcher in (state.home_pitcher, state.away_pitcher):
        if pitcher:
            player_map[pitcher.id] = pitcher

    for player_id, line in state.stats.items():
        player = player_map.get(player_id)
        if not player:
            continue
        drive = getattr(player, "drive", 50) or 50
        if drive >= 55:
            continue
        if _bad_batter_game(line) or _bad_pitcher_game(line):
            pressure = 0.25 + (55 - drive) / 120
            if random.random() < pressure:
                flag_player_slump(player)
                session.add(player)
                state.log(
                    f"SLUMP: {player.name} is pressing after that outing."
                )


def _bad_batter_game(line: dict) -> bool:
    at_bats = line.get("at_bats", 0)
    hits = line.get("hits", 0)
    strikeouts = line.get("strikeouts", 0)
    return at_bats >= 3 and hits == 0 and strikeouts >= 2


def _bad_pitcher_game(line: dict) -> bool:
    innings = line.get("innings_pitched", 0.0)
    runs = line.get("runs_allowed", 0)
    return innings >= 2.0 and runs >= 3
