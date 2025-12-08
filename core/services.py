from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from sqlalchemy.orm import Session


class SessionProvider:
    """Owns a lazily-created session without forcing callers to hold it globally."""

    def __init__(self, factory: Callable[[], Session], initial_session: Optional[Session] = None):
        self.factory = factory
        self._session: Optional[Session] = initial_session

    def get(self) -> Session:
        if self._session is None:
            self._session = self.factory()
        return self._session

    def refresh(self) -> Session:
        self.close()
        return self.get()

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None


class TempEffects:
    """Scoped store for temporary effects/buffs without coupling to GameContext."""

    def __init__(self, initial: Optional[Dict[str, Any]] = None):
        self._data: Dict[str, Any] = dict(initial or {})

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    def set(self, key: str, payload: Any) -> None:
        self._data[key] = payload

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def clear(self, key: str) -> None:
        self._data.pop(key, None)

    def clear_all(self) -> None:
        self._data.clear()
