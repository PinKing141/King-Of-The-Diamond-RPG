"""Service layer for spending ability points and unlocking talent nodes."""
from __future__ import annotations

from typing import Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from database.setup_db import Player
from game.systems import talent_tree


class TalentUnlockError(Exception):
    pass


def list_owned_talent_nodes(player: Player) -> Set[str]:
    """Return set of unlocked talent node keys for a player.

    Currently draws from Player.talent_nodes if present; extend to DB table when added.
    """
    owned = getattr(player, "talent_nodes", None)
    if owned is None:
        return set()
    if isinstance(owned, str):
        try:
            # Stored as comma-delimited or JSON-ish string
            return set([k.strip() for k in owned.split(",") if k.strip()])
        except Exception:
            return set()
    try:
        return set(owned)
    except TypeError:
        return set()


def spend_ability_points(player: Player, amount: int) -> None:
    if amount <= 0:
        return
    points = int(getattr(player, "ability_points", 0) or 0)
    if points < amount:
        raise TalentUnlockError("Not enough ability points.")
    player.ability_points = points - amount


def _persist_owned(player: Player, owned: Set[str]) -> None:
    # Until a dedicated PlayerTalent table exists, store as comma-separated string on player.
    player.talent_nodes = ",".join(sorted(owned))


def unlock_talent_node(session: Session, player: Player, node_key: str) -> Tuple[bool, str]:
    """Validate and unlock a talent node, persisting the change.

    Returns (success, message).
    """
    if not player:
        return False, "No player provided."

    owned = list_owned_talent_nodes(player)
    if node_key in owned:
        return False, "Node already unlocked."

    if not talent_tree.can_unlock_talent(player, node_key, owned_nodes=owned):
        return False, "Requirements not met or insufficient points."

    node = talent_tree.get_talent_node(node_key)
    if not node:
        return False, "Unknown talent node."

    try:
        spend_ability_points(player, node.cost)
    except TalentUnlockError as exc:
        return False, str(exc)

    owned.add(node_key)
    _persist_owned(player, owned)

    try:
        session.add(player)
        session.commit()
    except Exception as exc:
        session.rollback()
        return False, f"Failed to persist unlock: {exc}"
    return True, f"Unlocked {node.key} (Cost {node.cost})"


def get_player_talent_state(player: Player) -> dict:
    owned = list_owned_talent_nodes(player)
    return {
        "ability_points": int(getattr(player, "ability_points", 0) or 0),
        "owned_nodes": sorted(owned),
    }
