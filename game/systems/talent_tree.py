"""Lightweight talent tree helpers for the Phase 5 pitch arsenal update."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set

from core.paths import data_path
from game import pitch_types


def _get_stat(player, attr: str) -> float:
    value = getattr(player, attr, 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _metric_value(player, metric_key: str) -> float:
    metric = metric_key.lower()
    if metric == "grip_strength":
        return 0.6 * _get_stat(player, "power") + 0.4 * _get_stat(player, "determination")
    if metric == "finger_length":
        return 0.35 * max(0.0, _get_stat(player, "height_cm") - 150) + 0.65 * _get_stat(player, "movement")
    if metric == "spin_efficiency":
        return 0.5 * _get_stat(player, "control") + 0.5 * _get_stat(player, "movement")
    if metric == "feel_for_release":
        return 0.6 * _get_stat(player, "control") + 0.4 * _get_stat(player, "discipline")
    return _get_stat(player, metric)


@dataclass(frozen=True)
class TalentNode:
    key: str
    pitch_key: str
    tier: int
    description: str
    parents: Sequence[str]
    cost: int = 1


_TREE_CACHE: Dict[str, TalentNode] = {}


def _load_talent_tree() -> Dict[str, TalentNode]:
    if _TREE_CACHE:
        return _TREE_CACHE
    path = data_path("talent_tree.json")
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw_tree = json.load(handle)
    except FileNotFoundError:
        raw_tree = {}
    for key, payload in raw_tree.items():
        _TREE_CACHE[key] = TalentNode(
            key=key,
            pitch_key=payload.get("pitch_key", ""),
            tier=int(payload.get("tier", 0)),
            description=payload.get("description", ""),
            parents=tuple(payload.get("parents", ())),
            cost=int(payload.get("cost", 1)),
        )
    return _TREE_CACHE


def get_talent_node(node_key: str) -> Optional[TalentNode]:
    return _load_talent_tree().get(node_key)


def list_talent_nodes_by_tier(tier: int) -> List[TalentNode]:
    tree = _load_talent_tree()
    return [node for node in tree.values() if node.tier == tier]


def can_unlock_talent(player, node_key: str, owned_nodes: Optional[Iterable[str]] = None) -> bool:
    tree = _load_talent_tree()
    node = tree.get(node_key)
    if not node:
        return False
    owned: Set[str] = set(owned_nodes or [])
    if any(parent not in owned for parent in node.parents):
        return False
    ability_points = int(getattr(player, "ability_points", 0) or 0)
    if ability_points < node.cost:
        return False
    pitch_def = pitch_types.PITCH_DEFINITIONS.get(node.pitch_key)
    if not pitch_def:
        return False
    for stat, requirement in pitch_def.unlock_stats.items():
        if _get_stat(player, stat) < requirement:
            return False
    for metric, requirement in pitch_def.unlock_metrics.items():
        if _metric_value(player, metric) < requirement:
            return False
    return True
