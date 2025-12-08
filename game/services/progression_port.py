from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from core.services import SessionProvider
from database.setup_db import Player
from game.personnel.personality_effects import adjust_player_morale
from game.personnel.player_progression import (
    get_milestone_definitions,
    process_milestone_unlocks,
)
from game.mechanics.skill_system import check_and_grant_skills, list_player_skill_keys


class ProgressionPort(Protocol):
    """Abstraction for skills/milestones/morale side effects during training."""

    def grant_skills(self, player_id: int, *, owned_keys: Optional[set] = None) -> List[str]:
        ...

    def process_milestones(
        self,
        player_id: int,
        *,
        definitions_cache: Optional[dict] = None,
        stats_cache: Optional[Dict[str, float]] = None,
        owned_keys: Optional[set] = None,
    ) -> List:
        ...

    def adjust_morale(self, player_id: int, delta: int) -> None:
        ...


class SQLAlchemyProgressionService(ProgressionPort):
    """Thin adapter over existing progression utilities using SQLAlchemy sessions."""

    def __init__(self, session_provider: SessionProvider) -> None:
        self.session_provider = session_provider

    @property
    def session(self):
        return self.session_provider.get()

    def _load_player(self, player_id: int) -> Optional[Player]:
        return self.session.get(Player, player_id)

    def grant_skills(self, player_id: int, *, owned_keys: Optional[set] = None) -> List[str]:
        player = self._load_player(player_id)
        if not player:
            return []
        owned_keys = owned_keys or set(list_player_skill_keys(player))
        unlocked = check_and_grant_skills(self.session, player, owned_keys=owned_keys)
        self.session.flush()
        return unlocked

    def process_milestones(
        self,
        player_id: int,
        *,
        definitions_cache: Optional[dict] = None,
        stats_cache: Optional[Dict[str, float]] = None,
        owned_keys: Optional[set] = None,
    ) -> List:
        player = self._load_player(player_id)
        if not player:
            return []
        defs = definitions_cache or get_milestone_definitions()
        stats_cache = stats_cache or {}
        owned_keys = owned_keys or set(list_player_skill_keys(player))
        unlocks = process_milestone_unlocks(
            self.session,
            player,
            milestone_definitions=defs,
            stats_cache=stats_cache,
            owned_skill_keys=owned_keys,
        )
        self.session.flush()
        return list(unlocks)

    def adjust_morale(self, player_id: int, delta: int) -> None:
        player = self._load_player(player_id)
        if not player:
            return
        adjust_player_morale(player, delta)
        self.session.flush()
