"""Simple pub/sub event bus used to decouple logic and presentation layers."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, List, Optional

EventHandler = Callable[[Dict[str, Any]], None]


class EventBus:
    """In-memory event hub with very small surface area."""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, List[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Register a handler for an event."""
        if handler not in self._subscribers[event_name]:
            self._subscribers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        """Remove a previously registered handler."""
        handlers = self._subscribers.get(event_name)
        if not handlers:
            return
        if handler in handlers:
            handlers.remove(handler)
        if not handlers:
            self._subscribers.pop(event_name, None)

    def publish(self, event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Dispatch an event to all subscribers."""
        handlers = list(self._subscribers.get(event_name, ()))
        if not handlers:
            return
        data = payload or {}
        for handler in handlers:
            handler(data)

    def clear(self) -> None:
        """Remove all subscribers (useful for tests)."""
        self._subscribers.clear()


__all__ = ["EventBus"]
