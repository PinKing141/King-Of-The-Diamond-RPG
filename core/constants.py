"""Shared gameplay configuration for UI + simulation layers."""
from __future__ import annotations

from typing import Dict, Tuple

from core.config_loader import ConfigLoader


_BALANCE = ConfigLoader.get_section("fatigue_costs", {}) or {}
_METADATA = ConfigLoader.get_section("action_metadata", {}) or {}

# --- EXPORTS (Used by Scheduler & UI) --------------------------------------
ACTION_COSTS: Dict[str, int] = dict(_BALANCE)
ACTION_METADATA: Dict[str, Dict[str, str]] = dict(_METADATA)

ACTION_METADATA_DEFAULT = {"short": "????", "desc": "Unassigned slot.", "colour": "RESET"}

HEAVY_TRAINING_ACTIONS = {"train_power", "train_speed", "train_stamina"}
LIGHT_TRAINING_ACTIONS = {"train_control", "train_contact"}

# --- Mandatory Schedule Policies -------------------------------------------
MANDATORY_TEAM_POLICY: Dict[Tuple[int, int], str] = {
    (3, 1): "team_practice",  # Thursday afternoon
}

FIRST_STRING_WEEKEND: Dict[Tuple[int, int], str] = {
    (5, 0): "practice_match",
    (5, 1): "practice_match",
}

SECOND_STRING_WEEKEND: Dict[Tuple[int, int], str] = {
    (5, 0): "train_heavy",
    (5, 1): "b_team_match",
}

SQUAD_FIRST_STRING = "FIRST_STRING"
SQUAD_SECOND_STRING = "SECOND_STRING"
BENCH_WEEKEND: Dict[Tuple[int, int], str] = {
    (5, 0): "train_heavy",
    (5, 1): "team_practice",
}
