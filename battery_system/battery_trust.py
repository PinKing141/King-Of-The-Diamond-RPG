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