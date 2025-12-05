"""Lightweight analytics helpers for match telemetry."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from game.config_loader import ConfigLoader


DEFAULT_EVENT_NAME = "TELEMETRY_READY"
TelemetryEvent = Dict[str, Any]


def _clone_mapping(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    if not payload:
        return snapshot
    for key, value in payload.items():
        if isinstance(value, dict):
            snapshot[key] = value.copy()
        elif isinstance(value, list):
            snapshot[key] = list(value)
        else:
            snapshot[key] = value
    return snapshot


def _player_label(state: Any, player_id: Optional[int]) -> Optional[str]:
    if player_id is None:
        return None
    lookup = getattr(state, "player_lookup", {}) or {}
    player = lookup.get(player_id)
    if not player:
        return None
    return (
        getattr(player, "name", None)
        or getattr(player, "last_name", None)
        or getattr(player, "first_name", None)
    )


def get_actions_metadata() -> Dict[str, Dict[str, Any]]:
    """Return a copy of the balancing metadata block for schedule actions."""
    actions = ConfigLoader.get("actions", default={}) or {}
    metadata = actions.get("metadata", {}) if isinstance(actions, dict) else {}
    return {key: value.copy() for key, value in metadata.items() if isinstance(value, dict)}


def describe_action(action_key: str) -> Dict[str, Any]:
    """Fetch a single action descriptor while remaining resilient to missing keys."""
    metadata = get_actions_metadata()
    return metadata.get(action_key, {}).copy()


@dataclass
class TelemetryCollector:
    """Aggregates structured match events for downstream analysis."""

    events: List[TelemetryEvent] = field(default_factory=list)
    action_metadata: Dict[str, Dict[str, Any]] = field(default_factory=get_actions_metadata)

    def record_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> TelemetryEvent:
        entry = {"type": event_type, "payload": payload or {}}
        self.events.append(entry)
        return entry

    def record_inning(
        self,
        *,
        inning: int,
        top_runs: Optional[int],
        bottom_runs: Optional[int],
        skipped_bottom: bool,
    ) -> TelemetryEvent:
        payload = {
            "inning": inning,
            "top": top_runs,
            "bottom": bottom_runs,
            "skipped_bottom": skipped_bottom,
        }
        return self.record_event("inning_complete", payload)

    def record_walkoff(
        self,
        *,
        inning: int,
        runs_scored: int,
        detail: Optional[Dict[str, Any]] = None,
    ) -> TelemetryEvent:
        payload = {"inning": inning, "runs_scored": runs_scored, "detail": detail or {}}
        return self.record_event("walkoff", payload)

    def record_game_over(
        self,
        *,
        home_score: int,
        away_score: int,
        winner_id: Optional[int],
    ) -> TelemetryEvent:
        payload = {
            "home_score": home_score,
            "away_score": away_score,
            "winner_id": winner_id,
            "actions": _clone_mapping(self.action_metadata),
        }
        return self.record_event("game_over", payload)

    def record_confidence_swing(
        self,
        *,
        player_id: Optional[int],
        team_id: Optional[int],
        delta: float,
        inning: int,
        reason: Optional[str],
        player_name: Optional[str],
    ) -> TelemetryEvent:
        payload = {
            "player_id": player_id,
            "team_id": team_id,
            "delta": delta,
            "inning": inning,
            "reason": reason,
            "player_name": player_name,
        }
        return self.record_event("confidence_swing", payload)

    def record_umpire_tilt(
        self,
        *,
        home_team_id: Optional[int],
        away_team_id: Optional[int],
        tilt_map: Optional[Dict[int, Dict[str, int]]],
    ) -> TelemetryEvent:
        payload = {
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "tilt": _clone_mapping(tilt_map or {}),
        }
        return self.record_event("umpire_tilt", payload)


def ensure_collector(state: Any) -> TelemetryCollector:
    """Attach a collector to state if missing and return it."""
    collector = getattr(state, "telemetry", None)
    if isinstance(collector, TelemetryCollector):
        return collector
    collector = TelemetryCollector()
    setattr(state, "telemetry", collector)
    setattr(state, "analytics_log", collector.events)
    return collector


def capture_confidence_swing(state: Any, player_id: Optional[int], delta: float, *, reason: Optional[str]) -> None:
    if state is None or not delta:
        return
    collector = ensure_collector(state)
    team_id = (getattr(state, "player_team_map", {}) or {}).get(player_id)
    collector.record_confidence_swing(
        player_id=player_id,
        team_id=team_id,
        delta=delta,
        inning=getattr(state, "inning", 0),
        reason=reason,
        player_name=_player_label(state, player_id),
    )


def flush_telemetry(
    state: Any,
    *,
    sinks: Optional[List[Dict[str, Any]]] = None,
    event_name: Optional[str] = None,
) -> List[TelemetryEvent]:
    collector = getattr(state, "telemetry", None)
    if not isinstance(collector, TelemetryCollector):
        return []
    events = list(collector.events)
    targets = sinks or _resolve_targets(state, event_name or DEFAULT_EVENT_NAME)
    for target in targets:
        _dispatch_to_target(target, events, state)
    setattr(state, "last_telemetry_flush", {"count": len(events)})
    return events


def _resolve_targets(state: Any, event_name: str) -> List[Dict[str, Any]]:
    policy = getattr(state, "telemetry_policy", None) or {}
    custom = policy.get("targets") or getattr(state, "telemetry_targets", None)
    targets: List[Dict[str, Any]] = []
    if custom:
        for entry in custom:
            if isinstance(entry, dict):
                targets.append(entry.copy())
            elif callable(entry):
                targets.append({"type": "callable", "handler": entry})
        return targets

    file_path = policy.get("file_path") or getattr(state, "telemetry_output_path", None)
    if file_path:
        targets.append({"type": "file", "path": file_path})

    if policy.get("store_in_db") or getattr(state, "telemetry_store_in_db", False):
        targets.append({"type": "db"})

    bus = getattr(state, "event_bus", None)
    if bus:
        targets.append({
            "type": "event_bus",
            "event_name": policy.get("event_name") or getattr(state, "telemetry_event_name", event_name),
            "bus": bus,
        })

    if not targets:
        targets.append({"type": "noop"})
    return targets


def _dispatch_to_target(target: Dict[str, Any], events: List[TelemetryEvent], state: Any) -> bool:
    kind = target.get("type")
    if kind == "event_bus":
        bus = target.get("bus") or getattr(state, "event_bus", None)
        if not bus:
            return False
        bus.publish(target.get("event_name", DEFAULT_EVENT_NAME), {"events": events})
        return True
    if kind == "file":
        path = target.get("path")
        if not path:
            return False
        _write_file(Path(path), events)
        return True
    if kind == "db":
        session = target.get("session") or getattr(state, "db_session", None)
        if not session:
            return False
        _persist_to_gamestate(session, events)
        return True
    if kind == "callable":
        handler = target.get("handler")
        if callable(handler):
            handler(events, state)
            return True
    return False


def _write_file(path: Path, events: List[TelemetryEvent]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, ensure_ascii=True, indent=2), encoding="utf-8")


def _persist_to_gamestate(session, events: List[TelemetryEvent]) -> None:
    try:
        from database.setup_db import GameState
    except Exception:
        return
    row = session.query(GameState).first()
    if not row:
        return
    row.last_telemetry_blob = json.dumps(events)
    session.add(row)
