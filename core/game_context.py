from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from core.services import SessionProvider, TempEffects
from world.rivals import get_ledger, RivalMatchContext
from game.story import StoryTracker


logger = logging.getLogger(__name__)


@dataclass
class GameContext:
    """Holds mutable game state shared across systems."""

    session_factory: Callable[[], Session]
    player_id: Optional[int] = None
    school_id: Optional[int] = None
    temp_effects_init: Optional[Dict[str, Any]] = None
    session_provider: Optional[SessionProvider] = None
    story_tracker: StoryTracker = field(default_factory=StoryTracker)
    rivalry_ledger = get_ledger()
    _temp_effects_store: TempEffects = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.session_provider = self.session_provider or SessionProvider(self.session_factory)
        self._temp_effects_store = TempEffects(self.temp_effects_init)

    @property
    def session(self) -> Session:
        return self.session_provider.get()

    def refresh_session(self) -> None:
        self.session_provider.refresh()

    def close_session(self) -> None:
        self.session_provider.close()

    def set_player(self, player_id: int, school_id: Optional[int]) -> None:
        self.player_id = player_id
        self.school_id = school_id

    # --- Rivalry helpers ---
    def get_rival_context(
        self,
        hero_id: Optional[int],
        opponent_school_id: Optional[int],
    ) -> Optional[RivalMatchContext]:
        """Resolve a RivalMatchContext for the given opponent, if any.

        This is intentionally lightweight: we scan the opponent roster for a
        rival candidate (best overall fallback) and return a match context so
        downstream systems (match engine, UI) can react without hard DB wiring.
        """

        if not (hero_id and opponent_school_id and self.session):
            return None

        try:
            from database.setup_db import Player  # Lazy import to avoid cycles

            rival = (
                self.session.query(Player)
                .filter(Player.school_id == opponent_school_id)
                .order_by(Player.overall.desc())
                .first()
            )
            if not rival:
                return None

            return self.rivalry_ledger.create_match_context(
                hero_id=hero_id,
                rival_id=rival.id,
                hero_team_id=self.school_id,
                rival_team_id=opponent_school_id,
            )
        except SQLAlchemyError as exc:
            # Log and continue so rivalry detection doesn't fail silently.
            logger.warning("Rival lookup failed", exc_info=exc)
            return None

    # --- Temporary Buff Helpers ---
    @property
    def temp_effects_store(self) -> TempEffects:
        return self._temp_effects_store

    @property
    def temp_effects(self) -> Dict[str, Any]:
        return self._temp_effects_store.data

    @temp_effects.setter
    def temp_effects(self, payload: Optional[Dict[str, Any]]) -> None:
        # Allow dataclass init to assign temp_effects before store is built.
        if isinstance(getattr(self, "_temp_effects_store", None), TempEffects):
            self._temp_effects_store = TempEffects(payload)
        else:
            object.__setattr__(self, "_temp_effects_store", TempEffects(payload))

    def set_temp_effect(self, key: str, payload: Any) -> None:
        self._temp_effects_store.set(key, payload)

    def get_temp_effect(self, key: str, default=None):
        return self._temp_effects_store.get(key, default)

    def clear_temp_effect(self, key: str) -> None:
        self._temp_effects_store.clear(key)

    def clear_all_temp_effects(self) -> None:
        self._temp_effects_store.clear_all()
