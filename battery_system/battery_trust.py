"""Helpers that manage catcher-pitcher trust dynamics."""

from database.setup_db import BatteryTrust, session_scope


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _get_or_create_trust_record(session, pitcher_id, catcher_id):
    rec = session.get(BatteryTrust, (pitcher_id, catcher_id))
    if not rec:
        rec = BatteryTrust(pitcher_id=pitcher_id, catcher_id=catcher_id, trust=50)
        session.add(rec)
    return rec


def get_trust(pitcher_id, catcher_id):
    """Return the saved trust value for a battery pair, seeding it if missing."""
    if not pitcher_id or not catcher_id:
        return 50
    with session_scope() as session:
        rec = _get_or_create_trust_record(session, pitcher_id, catcher_id)
        session.commit()
        return rec.trust


def update_trust(pitcher_id, catcher_id, delta):
    """Modify the stored trust value and clamp it between 0 and 100."""
    if not pitcher_id or not catcher_id or not delta:
        return
    with session_scope() as session:
        rec = _get_or_create_trust_record(session, pitcher_id, catcher_id)
        rec.trust = max(0, min(100, rec.trust + delta))
        session.commit()


def update_trust_after_at_bat(pitcher_id, catcher_id, result_type):
    """Simple wrapper that bumps trust based on an at-bat outcome."""
    delta = 0
    if result_type == "K":
        delta = 1  # Strikeout builds trust
    elif result_type in ["1B", "2B", "3B", "HR"]:
        delta = -1  # Hits damage trust slightly
    elif result_type == "BB":
        delta = -1

    if delta != 0:
        update_trust(pitcher_id, catcher_id, delta)


def adjust_confidence_delta_for_battery(pitcher, catcher, delta: float) -> float:
    """Scale a confidence delta using catcher loyalty, trust, and pitcher volatility."""

    if not pitcher or not catcher or delta == 0:
        return delta

    loyalty = getattr(catcher, "loyalty", 50) or 50
    volatility = getattr(pitcher, "volatility", 50) or 50

    pitcher_id = getattr(pitcher, "id", None)
    catcher_id = getattr(catcher, "id", None)
    trust = get_trust(pitcher_id, catcher_id) if pitcher_id and catcher_id else 50

    loyalty_anchor = max(0.0, (loyalty - 55) / 40.0)
    trust_bonus = max(0.0, (trust - 50) / 30.0)
    volatility_push = max(0.0, (volatility - 55) / 35.0)

    calming = _clamp(loyalty_anchor + trust_bonus, 0.0, 1.2)
    agitation = _clamp(volatility_push, 0.0, 1.0)

    if delta < 0:
        scale = 1.0 - (calming * 0.45) + (agitation * 0.35)
    else:
        scale = 1.0 + (calming * 0.30) - (agitation * 0.25)

    return delta * _clamp(scale, 0.4, 1.6)