from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any
from sqlalchemy.orm import Session

from world.rivals import get_ledger, RivalMatchContext
from game.story import StoryTracker


@dataclass
class GameContext:
    """Holds mutable game state shared across systems."""

    session_factory: Callable[[], Session]
    player_id: Optional[int] = None
    school_id: Optional[int] = None
    _session: Optional[Session] = field(default=None, init=False, repr=False)
    temp_effects: Dict[str, Any] = field(default_factory=dict)
    rivalry_ledger = get_ledger()
    story_tracker: StoryTracker = field(default_factory=StoryTracker)

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = self.session_factory()
        return self._session

    def refresh_session(self) -> None:
        self.close_session()
        self._session = self.session_factory()

    def close_session(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

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
        except Exception:
            return None

    # --- Temporary Buff Helpers ---
    def set_temp_effect(self, key: str, payload: Any) -> None:
        self.temp_effects[key] = payload

    def get_temp_effect(self, key: str, default=None):
        return self.temp_effects.get(key, default)

    def clear_temp_effect(self, key: str) -> None:
        self.temp_effects.pop(key, None)

    def clear_all_temp_effects(self) -> None:
        self.temp_effects.clear()
