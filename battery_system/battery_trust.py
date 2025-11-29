# battery_system/battery_trust.py
from database.setup_db import BatteryTrust, session

def get_trust(pitcher_id, catcher_id):
    """
    Retrieves the current trust level between a battery pair.
    Default is 50.
    """
    trust_rec = session.query(BatteryTrust).get((pitcher_id, catcher_id))
    if not trust_rec:
        # Create new record if they haven't played together
        trust_rec = BatteryTrust(pitcher_id=pitcher_id, catcher_id=catcher_id, trust=50)
        session.add(trust_rec)
        session.commit()
    return trust_rec.trust

def update_trust(pitcher_id, catcher_id, delta):
    """
    Modifies trust by delta, clamped between 0 and 100.
    """
    trust_rec = session.query(BatteryTrust).get((pitcher_id, catcher_id))
    if not trust_rec:
        trust_rec = BatteryTrust(pitcher_id=pitcher_id, catcher_id=catcher_id, trust=50)
        session.add(trust_rec)
    
    trust_rec.trust = max(0, min(100, trust_rec.trust + delta))
    session.commit()
    # print(f"   (Trust updated: {trust_rec.trust} [{'+' if delta>0 else ''}{delta}])")

def update_trust_after_at_bat(pitcher_id, catcher_id, result_type):
    """
    Simple helper to adjust trust based on the result of an At-Bat.
    """
    delta = 0
    if result_type == "K":
        delta = 1 # Strikeout builds trust
    elif result_type in ["1B", "2B", "3B", "HR"]:
        delta = -1 # Hits damage trust slightly
    elif result_type == "BB":
        delta = -1
    
    if delta != 0:
        update_trust(pitcher_id, catcher_id, delta)