from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy.orm import Session

from core.io_interface import IOInterface
from database.setup_db import Player
from game.personnel.player_progression import apply_position_change_request

TRUST_GATE_DEFAULT = 80
TRUST_COST_DEFAULT = 15


def negotiate_position_change(
    session: Session,
    player: Player,
    target_position: str,
    *,
    io: Optional[IOInterface] = None,
    trust_gate: int = TRUST_GATE_DEFAULT,
    trust_cost: int = TRUST_COST_DEFAULT,
) -> Dict[str, object]:
    """Controller-friendly wrapper for coach-led position change requests.

    Returns a payload suitable for UI rendering without binding to any UI layer.
    Does not prompt for input; caller provides the target position.
    """

    if not player:
        return {"status": "error", "message": "No active player found."}
    if not target_position:
        return {"status": "error", "message": "No target position provided."}

    approved, message = apply_position_change_request(
        session,
        player,
        target_position,
        trust_gate=trust_gate,
        trust_cost=trust_cost,
    )

    status = "approved" if approved else "rejected"
    trust_delta = -trust_cost if approved else 0
    payload = {
        "status": status,
        "message": message,
        "player_id": getattr(player, "id", None),
        "secondary_position": getattr(player, "secondary_position", None),
        "trust_delta": trust_delta,
        "trust_after": getattr(player, "trust_baseline", None),
    }

    if io:
        level = "accent" if approved else "warning"
        io.log(message, level=level)

    return payload
