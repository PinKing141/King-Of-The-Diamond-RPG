"""Helpers that manage catcher-pitcher trust dynamics."""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from sqlalchemy.exc import OperationalError, PendingRollbackError

from database.setup_db import BatteryTrust, session_scope

_PLATE_RESULT_DELTAS = {
    "K": 1,
    "BB": -1,
    "1B": -1,
    "2B": -1,
    "3B": -1,
    "HR": -1,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ensure_cache(container) -> Optional[Dict[Tuple[int, int], int]]:
    if container is None:
        return None
    cache = getattr(container, "battery_trust_cache", None)
    if cache is None:
        cache = {}
        setattr(container, "battery_trust_cache", cache)
    return cache


def _ensure_sync_tracker(container) -> Optional[Dict[Tuple[int, int], float]]:
    if container is None:
        return None
    tracker = getattr(container, "battery_sync", None)
    if tracker is None:
        tracker = {}
        setattr(container, "battery_sync", tracker)
    return tracker


def _get_or_create_trust_record(session, pitcher_id, catcher_id):
    rec = session.get(BatteryTrust, (pitcher_id, catcher_id))
    if not rec:
        rec = BatteryTrust(pitcher_id=pitcher_id, catcher_id=catcher_id, trust=50)
        session.add(rec)
    return rec


def _commit_with_retry(session, retries: int = 5, delay: float = 0.1) -> None:
    """Handle transient sqlite database locks by retrying commits."""

    for attempt in range(retries):
        try:
            session.commit()
            return
        except OperationalError as exc:  # sqlite database locked
            session.rollback()
            if "database is locked" not in str(exc).lower() or attempt == retries - 1:
                raise
            time.sleep(delay)
        except PendingRollbackError:
            session.rollback()
        except Exception:
            session.rollback()
            raise


def get_trust(pitcher_id, catcher_id):
    """Return the saved trust value for a battery pair, seeding it if missing."""
    if not pitcher_id or not catcher_id:
        return 50
    with session_scope() as session:
        rec = session.get(BatteryTrust, (pitcher_id, catcher_id))
        if rec is None:
            rec = _get_or_create_trust_record(session, pitcher_id, catcher_id)
            _commit_with_retry(session)
        return rec.trust


def update_trust(pitcher_id, catcher_id, delta):
    """Modify the stored trust value and clamp it between 0 and 100."""
    if not pitcher_id or not catcher_id or not delta:
        return None
    with session_scope() as session:
        rec = _get_or_create_trust_record(session, pitcher_id, catcher_id)
        rec.trust = max(0, min(100, rec.trust + delta))
        _commit_with_retry(session)
        return rec.trust


def trust_delta_for_plate_result(*, result_type: Optional[str], hit_type: Optional[str] = None) -> int:
    """Translate a plate appearance outcome into the trust delta without persisting it."""

    token = _plate_result_token(result_type, hit_type)
    if not token:
        return 0
    return _PLATE_RESULT_DELTAS.get(token, 0)


def update_trust_after_at_bat(pitcher_id, catcher_id, result_type):
    """Simple wrapper that bumps trust based on an at-bat outcome."""
    delta = _PLATE_RESULT_DELTAS.get(result_type, 0)
    if delta != 0:
        return update_trust(pitcher_id, catcher_id, delta)
    return None


def adjust_confidence_delta_for_battery(pitcher, catcher, delta: float) -> float:
    """Scale confidence swings based on catcher loyalty, battery trust, and pitcher volatility."""

    if not pitcher or not catcher or delta == 0:
        return delta

    loyalty = getattr(catcher, "loyalty", 50) or 50
    volatility = getattr(pitcher, "volatility", 50) or 50

    pitcher_id = getattr(pitcher, "id", None)
    catcher_id = getattr(catcher, "id", None)
    trust = get_trust(pitcher_id, catcher_id) if pitcher_id and catcher_id else 50

    loyalty_factor = (loyalty - 50) / 50.0
    volatility_factor = (volatility - 50) / 50.0
    trust_factor = (trust - 50) / 50.0

    loyalty_factor = _clamp(loyalty_factor, -1.0, 1.0)
    volatility_factor = _clamp(volatility_factor, -1.0, 1.0)
    trust_factor = _clamp(trust_factor, -1.0, 1.0)

    if delta > 0:
        # High loyalty + trust boost positive moments, volatile pitchers dampen it.
        scale = 1.0 + (loyalty_factor * 0.35) + (trust_factor * 0.25) - (volatility_factor * 0.30)
    else:
        # Negative swings are softened by loyalty/trust but amplified by volatility.
        scale = 1.0 - (loyalty_factor * 0.30) - (trust_factor * 0.15) + (volatility_factor * 0.45)

    return delta * _clamp(scale, 0.35, 1.75)


def get_trust_snapshot(container, pitcher_id: Optional[int], catcher_id: Optional[int], default: int = 50) -> int:
    """Fetch trust once per game and reuse it via the provided cache container."""

    if not pitcher_id or not catcher_id:
        return default
    cache = _ensure_cache(container)
    key = (pitcher_id, catcher_id)
    if cache is not None and key in cache:
        return cache[key]
    value = get_trust(pitcher_id, catcher_id)
    if cache is not None:
        cache[key] = value
    return value


def set_trust_snapshot(container, pitcher_id: Optional[int], catcher_id: Optional[int], trust_value: Optional[int]) -> None:
    if not pitcher_id or not catcher_id or trust_value is None:
        return
    cache = _ensure_cache(container)
    if cache is None:
        return
    cache[(pitcher_id, catcher_id)] = int(_clamp(trust_value, 0, 100))


def apply_plate_result_to_trust(
    container,
    pitcher_id: Optional[int],
    catcher_id: Optional[int],
    *,
    result_type: Optional[str],
    hit_type: Optional[str] = None,
) -> Optional[int]:
    """Translate a plate appearance summary into a trust adjustment and persist it."""

    token = _plate_result_token(result_type, hit_type)
    if not token:
        return None
    new_value = update_trust_after_at_bat(pitcher_id, catcher_id, token)
    if new_value is not None:
        set_trust_snapshot(container, pitcher_id, catcher_id, new_value)
    return new_value


def _plate_result_token(result_type: Optional[str], hit_type: Optional[str]) -> Optional[str]:
    if not result_type:
        return None
    normalized = result_type.lower()
    if normalized == "strikeout":
        return "K"
    if normalized == "walk":
        return "BB"
    if hit_type:
        code = hit_type.upper()
        if code in {"1B", "2B", "3B", "HR"}:
            return code
    return None


def get_battery_sync(container, pitcher_id: Optional[int], catcher_id: Optional[int]) -> float:
    if not pitcher_id or not catcher_id:
        return 0.0
    tracker = _ensure_sync_tracker(container)
    if tracker is None:
        return 0.0
    return tracker.get((pitcher_id, catcher_id), 0.0)


def adjust_battery_sync(container, pitcher_id: Optional[int], catcher_id: Optional[int], delta: float) -> float:
    if not pitcher_id or not catcher_id or not delta:
        return get_battery_sync(container, pitcher_id, catcher_id)
    tracker = _ensure_sync_tracker(container)
    if tracker is None:
        return 0.0
    key = (pitcher_id, catcher_id)
    new_value = tracker.get(key, 0.0) + delta
    new_value = _clamp(new_value, -5.0, 5.0)
    tracker[key] = new_value
    return new_value


def apply_trust_buffer(buffer: Dict[Tuple[int, int], int]) -> None:
    """Commit aggregated trust deltas for a single game using one DB session."""

    if not buffer:
        return

    for attempt in range(5):
        try:
            with session_scope() as session:
                with session.no_autoflush:
                    for (pitcher_id, catcher_id), delta in buffer.items():
                        if not delta:
                            continue
                        rec = _get_or_create_trust_record(session, pitcher_id, catcher_id)
                        rec.trust = int(_clamp((rec.trust or 0) + delta, 0, 100))
                _commit_with_retry(session)
                return
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == 4:
                raise
            time.sleep(0.1 * (attempt + 1))