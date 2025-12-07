from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any
from sqlalchemy.orm import Session


@dataclass
class GameContext:
    """Holds mutable game state shared across systems."""

    session_factory: Callable[[], Session]
    player_id: Optional[int] = None
    school_id: Optional[int] = None
    _session: Optional[Session] = field(default=None, init=False, repr=False)
    temp_effects: Dict[str, Any] = field(default_factory=dict)

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

    # --- Temporary Buff Helpers ---
    def set_temp_effect(self, key: str, payload: Any) -> None:
        self.temp_effects[key] = payload

    def get_temp_effect(self, key: str, default=None):
        return self.temp_effects.get(key, default)

    def clear_temp_effect(self, key: str) -> None:
        self.temp_effects.pop(key, None)

    def clear_all_temp_effects(self) -> None:
        self.temp_effects.clear()
