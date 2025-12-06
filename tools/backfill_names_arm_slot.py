"""Backfill existing saves to enforce last-first naming and ensure arm_slot is set.

Run once as a maintenance script. It will:
- Normalize Player.name to "Last First" when both parts exist.
- Ensure arm_slot is populated (default Three-Quarters) for pitchers missing it.

Usage (from repo root):
  python -m tools.backfill_names_arm_slot
"""

from __future__ import annotations

from sqlalchemy import update

from database.setup_db import get_session, Player


def main():
    session = get_session()
    updated = 0
    try:
        players = session.query(Player).all()
        for p in players:
            # Backfill arm slot for pitchers
            if (p.position or "").lower().startswith("pitch") and not getattr(p, "arm_slot", None):
                p.arm_slot = "Three-Quarters"
            # Normalize name display to last-first when both parts exist
            ln = (p.last_name or "").strip()
            fn = (p.first_name or "").strip()
            if ln and fn:
                new_name = f"{ln} {fn}"
                if p.name != new_name:
                    p.name = new_name
            elif ln and not fn and p.name:
                # If we only have last name, keep existing name
                pass
            elif fn and not ln and p.name != fn:
                p.name = fn
            updated += 1
        session.commit()
        print(f"Backfill complete. Updated {updated} player records.")
    finally:
        session.close()


if __name__ == "__main__":
    main()