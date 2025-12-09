"""Structured logging helpers for simulation lifecycle events."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional


def log_event(event_type: str, *, logger: Optional[logging.Logger] = None, level: str = "info", **fields: Any) -> None:
    """Emit a structured log payload for sim lifecycle events.

    Payload shape: {"event": event_type, **fields}
    """

    payload: Dict[str, Any] = {"event": event_type}
    payload.update(fields)
    sink = logger or logging.getLogger("world_sim.lifecycle")
    log_fn = getattr(sink, level, sink.info)
    log_fn(payload)
