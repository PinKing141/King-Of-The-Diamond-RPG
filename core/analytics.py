"""Centralised analytics sink that listens for telemetry events and buffers them."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.event_bus import EventBus

TELEMETRY_EVENT = "TELEMETRY_READY"
PHASE_EVENT = "MATCH_STATE_CHANGE"
_DEFAULT_BUFFER = 50
_FLUSH_PHASES = {"INNING_READY", "INNING_HALF", "INNING_BREAK", "GAME_OVER"}


class _AnalyticsRecorder:
    """Collects telemetry payloads and flushes them to sinks on demand."""

    def __init__(
        self,
        bus: EventBus,
        *,
        buffer_size: int = _DEFAULT_BUFFER,
        file_path: Optional[str] = None,
    ) -> None:
        self.bus = bus
        self.buffer_size = max(1, buffer_size)
        self.buffer: List[Dict[str, Any]] = []
        self.file_path = Path(file_path).expanduser().resolve() if file_path else None
        self.last_flush_ts: Optional[float] = None
        self.bus.subscribe(TELEMETRY_EVENT, self._on_telemetry_ready)
        self.bus.subscribe(PHASE_EVENT, self._on_phase_change)

    def _on_telemetry_ready(self, payload: Optional[Dict[str, Any]]) -> None:
        events = []
        if payload:
            raw = payload.get("events")
            if isinstance(raw, list):
                events = [event for event in raw if isinstance(event, dict)]
        if not events:
            return
        self.buffer.extend(events)
        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def _on_phase_change(self, payload: Optional[Dict[str, Any]]) -> None:
        if not payload:
            return
        phase = payload.get("phase")
        if phase in _FLUSH_PHASES:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        if self.file_path:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("a", encoding="utf-8") as handle:
                for event in self.buffer:
                    handle.write(json.dumps(event, ensure_ascii=True) + "\n")
        self.last_flush_ts = time.time()
        self.buffer.clear()


def initialise_analytics(
    event_bus: Optional[EventBus] = None,
    *,
    buffer_size: int = _DEFAULT_BUFFER,
    file_path: Optional[str] = None,
) -> EventBus:
    """Attach analytics listeners to the supplied bus and return it."""

    bus = event_bus or EventBus()
    _AnalyticsRecorder(bus, buffer_size=buffer_size, file_path=file_path)
    return bus


__all__ = ["initialise_analytics", "TELEMETRY_EVENT"]
