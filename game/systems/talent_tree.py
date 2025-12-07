"""Lightweight talent tree helpers for the Phase 5 pitch arsenal update."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set

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


TALENT_TREE: Dict[str, TalentNode] = {
    "pitch_four_seam": TalentNode(
        key="pitch_four_seam",
        pitch_key="four_seam_fastball",
        tier=1,
        description="Foundation heater unlocked via basic fastball work.",
        parents=(),
        cost=1,
    ),
    "pitch_two_seam": TalentNode(
        key="pitch_two_seam",
        pitch_key="two_seam_fastball",
        tier=1,
        description="Adds arm-side run to the repertoire.",
        parents=(),
        cost=1,
    ),
    "pitch_slider": TalentNode(
        key="pitch_slider",
        pitch_key="slider",
        tier=2,
        description="Sharp glove-side bite unlocked after fastball foundation.",
        parents=("pitch_four_seam",),
        cost=2,
    ),
    "pitch_curveball": TalentNode(
        key="pitch_curveball",
        pitch_key="curveball",
        tier=2,
        description="Big depth breaker for players who trust their two-seamer.",
        parents=("pitch_two_seam",),
        cost=2,
    ),
    "pitch_changeup": TalentNode(
        key="pitch_changeup",
        pitch_key="changeup",
        tier=2,
        description="Off-speed feel unlocked once the heater is under control.",
        parents=("pitch_four_seam",),
        cost=2,
    ),
    "pitch_cutter_custom": TalentNode(
        key="pitch_cutter_custom",
        pitch_key="cutter_custom",
        tier=3,
        description="Signature cutter that branches off the two-seam/slider duo.",
        parents=("pitch_two_seam", "pitch_slider"),
        cost=3,
    ),
    "pitch_splitter": TalentNode(
        key="pitch_splitter",
        pitch_key="splitter",
        tier=3,
        description="Forkball-inspired dive unlocked after mastering the changeup.",
        parents=("pitch_changeup",),
        cost=3,
    ),
    "pitch_knuckleball": TalentNode(
        key="pitch_knuckleball",
        pitch_key="knuckleball",
        tier=3,
        description="Chaos pitch rewarded to those with relentless focus.",
        parents=("pitch_curveball",),
        cost=3,
    ),
}


def get_talent_node(node_key: str) -> Optional[TalentNode]:
    return TALENT_TREE.get(node_key)


def list_talent_nodes_by_tier(tier: int) -> List[TalentNode]:
    return [node for node in TALENT_TREE.values() if node.tier == tier]


def can_unlock_talent(player, node_key: str, owned_nodes: Optional[Iterable[str]] = None) -> bool:
    node = TALENT_TREE.get(node_key)
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
