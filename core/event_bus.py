"""Simple pub/sub event bus used to decouple logic and presentation layers."""
from __future__ import annotations

import logging
from collections import defaultdict
from enum import Enum
from typing import Any, Callable, DefaultDict, Dict, List, Optional, Union

EventKey = Union[str, Enum]
EventHandler = Callable[[Dict[str, Any]], None]

logger = logging.getLogger(__name__)


class EventBus:
    """In-memory event hub with very small surface area."""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, List[EventHandler]] = defaultdict(list)

    def _key(self, event_name: EventKey) -> str:
        return event_name.value if isinstance(event_name, Enum) else str(event_name)

    def subscribe(self, event_name: EventKey, handler: EventHandler) -> None:
        """Register a handler for an event."""
        key = self._key(event_name)
        if handler not in self._subscribers[key]:
            self._subscribers[key].append(handler)

    def unsubscribe(self, event_name: EventKey, handler: EventHandler) -> None:
        """Remove a previously registered handler."""
        key = self._key(event_name)
        handlers = self._subscribers.get(key)
        if not handlers:
            return
        if handler in handlers:
            handlers.remove(handler)
        if not handlers:
            self._subscribers.pop(key, None)

    def publish(self, event_name: EventKey, payload: Optional[Dict[str, Any]] = None) -> None:
        """Dispatch an event to all subscribers."""
        key = self._key(event_name)
        handlers = list(self._subscribers.get(key, ()))
        if not handlers:
            return
        data = payload or {}
        for handler in handlers:
            try:
                handler(data)
            except Exception as exc:  # Defensive guard so one bad handler doesn't cascade
                logger.warning("EventBus handler failed for '%s'", key, exc_info=exc)

    def clear(self) -> None:
        """Remove all subscribers (useful for tests)."""
        self._subscribers.clear()


__all__ = ["EventBus"]
