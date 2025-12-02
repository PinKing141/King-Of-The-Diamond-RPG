"""API Bridge entry point for GUI (Godot/Web) clients.

This module centralizes every callable operation that the eventual UI will invoke.
Each function must:
  * Accept and return JSON-serializable payloads (dict/list/primitive only).
  * Never print or read from stdin; treat inputs as already validated payloads.
  * Wrap errors in the shared `api_error` schema so the UI can respond gracefully.

The initial surface documented below is intentionally small; add or adjust routes here
as more Phase 9 milestones come online.
"""
from __future__ import annotations

import logging
import random
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from database.setup_db import get_session, School
from game.create_player import (
    DEFAULT_PITCH_ARSENAL,
    MAX_PITCHES,
    MIN_PITCHES,
    PITCH_SELECTION_POOL,
    commit_player_to_db,
    roll_stats,
)
from game.game_context import GameContext
from game.save_manager import get_save_slots, load_game, save_game
from game.weekly_scheduler_core import execute_schedule_core

LOG = logging.getLogger(__name__)

API_SURFACE: Dict[str, str] = {
    "ping": "Connectivity check for the GUI client.",
    "create_player_preview": "Return rolls + metadata for a prospective hero without persisting.",
    "commit_player_profile": "Persist a prepared hero profile to the database.",
    "simulate_week": "Run weekly scheduler + sims (placeholder).",
    "list_save_states": "Enumerate available saves for the UI selector.",
    "save_game_slot": "Persist the current DB snapshot into a numbered slot.",
    "load_game_slot": "Restore the DB snapshot from a numbered slot.",
}


class ApiError(Exception):
    """Structured exception that the GUI can surface cleanly."""

    def __init__(self, code: str, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_payload(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


def _ok(data: Any = None) -> Dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _fail(error: ApiError) -> Dict[str, Any]:
    return {"ok": False, "data": None, "error": error.to_payload()}


@contextmanager
def _session_scope() -> Generator:
    session = get_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _run(handler: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    """Wrapper to standardize error handling for exported API calls."""

    try:
        return handler()
    except ApiError as api_exc:
        LOG.warning("API error: %s", api_exc)
        return _fail(api_exc)
    except Exception as exc:  # pragma: no cover - surface unknowns cleanly
        LOG.exception("Unhandled API exception")
        return _fail(ApiError("internal_error", "Unexpected server error", {"detail": str(exc)}))


INFIELD_POSITIONS = {"First Base", "Second Base", "Third Base", "Shortstop"}
OUTFIELD_POSITIONS = {"Left Field", "Center Field", "Right Field"}
SPECIFIC_TO_GENERAL = {
    "Pitcher": "Pitcher",
    "Catcher": "Catcher",
    **{pos: "Infielder" for pos in INFIELD_POSITIONS},
    **{pos: "Outfielder" for pos in OUTFIELD_POSITIONS},
}
GENERAL_POSITIONS = {"Pitcher", "Catcher", "Infielder", "Outfielder"}


def _resolve_position(payload: Dict[str, Any], *, require_specific: bool) -> Tuple[str, Optional[str]]:
    specific = payload.get("specific_position") or payload.get("specific_pos")
    if specific:
        general = SPECIFIC_TO_GENERAL.get(specific)
        if not general:
            raise ApiError("invalid_specific_position", f"Unsupported position: {specific}")
        return general, specific

    position = payload.get("position")
    if not position:
        raise ApiError("missing_position", "Payload must include 'position'.")
    if position not in GENERAL_POSITIONS:
        raise ApiError("invalid_position", f"Position must be one of {sorted(GENERAL_POSITIONS)}")
    if require_specific and position in {"Infielder", "Outfielder"}:
        raise ApiError("specific_required", "Provide 'specific_position' for this role.")
    default_specific = position if position in {"Pitcher", "Catcher"} else None
    return position, default_specific


def _roll_stats_for_preview(position: str, seed: Optional[Any]) -> Dict[str, Any]:
    if seed is None:
        return roll_stats(position)
    try:
        seed_value = int(seed)
    except (TypeError, ValueError):
        raise ApiError("invalid_seed", "reroll_seed must be an integer")
    state = random.getstate()
    random.seed(seed_value)
    try:
        return roll_stats(position)
    finally:
        random.setstate(state)


def _growth_style_choices(position: str) -> List[str]:
    if position == "Pitcher":
        return ["Power Pitcher", "Technical Pitcher", "Fierce Pitcher", "Marathon Pitcher", "Balanced"]
    if position == "Catcher":
        return ["Offensive Catcher", "Defensive General", "Balanced"]
    return ["Power Hitter", "Speedster", "Balanced"]


def _sanitize_pitch_selection(selection: Optional[List[str]]) -> List[str]:
    if not selection:
        return []
    sanitized: List[str] = []
    for pitch in selection:
        if isinstance(pitch, str) and pitch in PITCH_SELECTION_POOL and pitch not in sanitized:
            sanitized.append(pitch)
        if len(sanitized) >= MAX_PITCHES:
            break
    return sanitized


def _validate_schedule_grid(schedule) -> List[List[Optional[str]]]:
    if not isinstance(schedule, list) or len(schedule) != 7:
        raise ApiError("invalid_schedule", "Schedule must contain 7 days.")
    normalized: List[List[Optional[str]]] = []
    for day_idx, day in enumerate(schedule):
        if not isinstance(day, list) or len(day) != 3:
            raise ApiError("invalid_schedule", f"Day {day_idx} must contain 3 slots.")
        normalized_day: List[Optional[str]] = []
        for slot_idx, action in enumerate(day):
            if action is None:
                normalized_day.append(None)
            elif isinstance(action, str):
                normalized_day.append(action)
            else:
                raise ApiError(
                    "invalid_schedule",
                    f"Action at day {day_idx} slot {slot_idx} must be a string or null.",
                )
        normalized.append(normalized_day)
    return normalized


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError("invalid_field", f"{field} must be a non-empty string")
    return value.strip()


def _require_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError("invalid_field", f"{field} must be an integer")


def _serialize_training_details(details: Optional[dict]) -> Optional[dict]:
    if details is None:
        return None
    if not isinstance(details, dict):
        return {"value": str(details)}

    def _convert(value: Any):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [_convert(item) for item in value]
        if isinstance(value, dict):
            return {str(k): _convert(v) for k, v in value.items()}
        return str(value)

    return {str(k): _convert(v) for k, v in details.items()}


# ────────────────────────────────
# Public API Functions
# ────────────────────────────────

def ping() -> Dict[str, Any]:
    """Simple readiness probe so the GUI can ensure the bridge is alive."""

    return _run(lambda: _ok({"status": "ready", "version": "phase9-preview"}))


def create_player_preview(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll stats + metadata from existing generators without saving to DB.

    Args:
        payload: Expected keys:
            * position (str) – one of the supported role labels.
            * growth_style (optional str) – if omitted, default logic is applied.
            * reroll_seed (optional int) – when provided, RNG will be seeded for deterministic previews.

    Returns:
        JSON response with the rolled stats or an error contract.
    """

    def handler() -> Dict[str, Any]:
        data = payload or {}
        if not isinstance(data, dict):
            raise ApiError("invalid_request", "Payload must be a dict")

        position, specific = _resolve_position(data, require_specific=False)
        stats = _roll_stats_for_preview(position, data.get("reroll_seed"))
        preview = {
            "position": position,
            "specific_position": specific,
            "stats": stats,
            "growth_style_choices": _growth_style_choices(position),
            "starter_trait_odds": 0.35 if position == "Pitcher" else 0.0,
        }
        if position == "Pitcher":
            preview["default_pitch_arsenal"] = DEFAULT_PITCH_ARSENAL
            preview["pitch_pool"] = PITCH_SELECTION_POOL
        return _ok(preview)

    return _run(handler)


def commit_player_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a previously previewed player.

    Expects the GUI to send the fully-prepared profile in the same structure that
    `game.create_player.commit_player_to_db` consumes.
    """

    def handler() -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApiError("invalid_request", "Payload must be a dict")

        position, specific = _resolve_position(payload, require_specific=True)
        first = _require_text(payload.get("first_name"), "first_name")
        last = _require_text(payload.get("last_name"), "last_name")
        hometown = _require_text(payload.get("hometown") or "Tokyo", "hometown")
        stats = payload.get("stats")
        if not isinstance(stats, dict) or not stats:
            raise ApiError("invalid_stats", "'stats' must be a populated object")
        school_id = _require_int(payload.get("school_id"), "school_id")

        pitch_list = _sanitize_pitch_selection(payload.get("pitch_arsenal"))
        if position == "Pitcher":
            if len(pitch_list) < MIN_PITCHES:
                raise ApiError(
                    "invalid_pitch_arsenal",
                    f"Pitchers must submit at least {MIN_PITCHES} pitches from the approved pool.",
                )
        else:
            pitch_list = []

        starter_trait = bool(payload.get("starter_trait")) if position == "Pitcher" else False

        with _session_scope() as session:
            school = session.get(School, school_id)
            if not school:
                raise ApiError("invalid_school", "School not found", {"school_id": school_id})

            creation_payload = {
                "first_name": first,
                "last_name": last,
                "position": position,
                "specific_pos": specific,
                "growth_style": payload.get("growth_style") or "Balanced",
                "stats": stats,
                "hometown": hometown,
                "school": school,
                "rerolls_left": payload.get("rerolls_left", 0),
                "pitch_arsenal": pitch_list,
                "starter_trait": starter_trait,
            }

            player_id = commit_player_to_db(session, creation_payload)
            return _ok({"player_id": player_id})

    return _run(handler)


def simulate_week(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute the weekly schedule core loop and return structured results."""

    def handler() -> Dict[str, Any]:
        data = payload or {}
        if not isinstance(data, dict):
            raise ApiError("invalid_request", "Payload must be a dict")

        player_id = _require_int(data.get("player_id"), "player_id")
        school_id = _require_int(data.get("school_id"), "school_id")
        schedule_grid = _validate_schedule_grid(data.get("schedule"))
        current_week = _require_int(data.get("current_week", 1), "current_week")

        context = GameContext(get_session)
        context.set_player(player_id, school_id)
        try:
            execution = execute_schedule_core(context, schedule_grid, current_week)
        finally:
            context.close_session()

        results_payload = []
        for slot in execution.results:
            results_payload.append(
                {
                    "day_index": slot.day_index,
                    "slot_index": slot.slot_index,
                    "day": slot.day_name,
                    "slot": slot.slot_name,
                    "action": slot.action,
                    "summary": slot.training_summary,
                    "opponent": slot.opponent_name,
                    "match_result": slot.match_result,
                    "match_score": slot.match_score,
                    "error": slot.error,
                    "training_details": _serialize_training_details(slot.training_details),
                }
            )

        return _ok({"results": results_payload, "warnings": execution.warnings})

    return _run(handler)


def list_save_states() -> Dict[str, Any]:
    """Return available save metadata for the GUI load screen."""

    def handler() -> Dict[str, Any]:
        return _ok({"saves": get_save_slots()})

    return _run(handler)


def save_game_slot(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist the active DB snapshot into a numbered slot."""

    def handler() -> Dict[str, Any]:
        data = payload or {}
        if not isinstance(data, dict):
            raise ApiError("invalid_request", "Payload must be a dict")
        slot = _require_int(data.get("slot"), "slot")

        success, message = save_game(slot)
        if not success:
            raise ApiError("save_failed", message, {"slot": slot})
        return _ok({"slot": slot, "message": message})

    return _run(handler)


def load_game_slot(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Restore the active DB snapshot from a numbered slot."""

    def handler() -> Dict[str, Any]:
        data = payload or {}
        if not isinstance(data, dict):
            raise ApiError("invalid_request", "Payload must be a dict")
        slot = _require_int(data.get("slot"), "slot")

        success, message = load_game(slot)
        if not success:
            raise ApiError("load_failed", message, {"slot": slot})
        return _ok({"slot": slot, "message": message})

    return _run(handler)
