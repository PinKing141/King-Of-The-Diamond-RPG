from __future__ import annotations

from typing import Protocol, Optional

from game.dto import PlayerDTO, TeamDTO


class PlayerRepository(Protocol):
    def get(self, player_id: int) -> Optional[PlayerDTO]: ...

    def save(self, player: PlayerDTO) -> None: ...


class TeamRepository(Protocol):
    def get(self, team_id: int) -> Optional[TeamDTO]: ...
