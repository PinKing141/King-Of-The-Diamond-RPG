from __future__ import annotations

from typing import Protocol, Sequence, Optional

from game.services.dtos import PlayerTrainingDTO, TeamDTO


class PlayerRepository(Protocol):
    """Abstract persistence boundary for player data."""

    def get_active_player(self) -> Optional[PlayerTrainingDTO]:
        ...

    def save_player(self, payload: PlayerTrainingDTO) -> None:
        ...


class TeamRepository(Protocol):
    """Abstract persistence boundary for team data."""

    def get_team(self, team_id: int) -> Optional[TeamDTO]:
        ...

    def sample_practice_opponents(self, exclude_team_id: int, sample_size: int | None = None) -> Sequence[TeamDTO]:
        ...
