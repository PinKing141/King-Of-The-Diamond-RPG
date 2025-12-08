from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy.orm import Session

from core.repositories import PlayerRepository, TeamRepository
from core.services import SessionProvider
from database.setup_db import GameState, Player, Team
from game.services import mappers
from game.services.dtos import PlayerTrainingDTO, TeamDTO


class SQLAlchemyPlayerRepository(PlayerRepository):
    """SQLAlchemy-backed Player repository producing training DTOs."""

    def __init__(self, session_provider: SessionProvider) -> None:
        self.session_provider = session_provider

    @property
    def session(self) -> Session:
        return self.session_provider.get()

    def get_active_player(self) -> Optional[PlayerTrainingDTO]:
        state = self.session.query(GameState).first()
        if not state or not state.active_player_id:
            return None
        player = self.session.get(Player, state.active_player_id)
        if not player:
            return None
        return mappers.player_to_training_dto(player)

    def save_player(self, payload: PlayerTrainingDTO) -> None:
        if not payload.id:
            raise ValueError("Cannot save player without id")
        player = self.session.get(Player, payload.id)
        if not player:
            raise ValueError(f"Player {payload.id} not found")
        mappers.apply_training_dto_to_player(player, payload)
        self.session.add(player)
        self.session.flush()


class SQLAlchemyTeamRepository(TeamRepository):
    """SQLAlchemy-backed Team repository for training/match utilities."""

    def __init__(self, session_provider: SessionProvider) -> None:
        self.session_provider = session_provider

    @property
    def session(self) -> Session:
        return self.session_provider.get()

    def get_team(self, team_id: int) -> Optional[TeamDTO]:
        team = self.session.get(Team, team_id)
        if not team:
            return None
        return mappers.team_to_dto(team)

    def sample_practice_opponents(self, exclude_team_id: int, sample_size: int | None = None) -> Sequence[TeamDTO]:
        query = self.session.query(Team).filter(Team.id != exclude_team_id)
        if sample_size is not None and sample_size > 0:
            teams = query.order_by(Team.id).limit(sample_size).all()
        else:
            teams = query.all()
        return [mappers.team_to_dto(team) for team in teams]
