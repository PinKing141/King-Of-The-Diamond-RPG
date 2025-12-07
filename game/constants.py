"""Shared gameplay configuration for UI + simulation layers."""
from __future__ import annotations

import json
import os
from typing import Dict, Tuple


def _load_balancing_data():
    """Load balancing data from data/balancing.json with a small fallback."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, "data", "balancing.json")
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "fatigue_costs": {"rest": -15, "team_practice": 20},
            "action_metadata": {"rest": {"short": "REST", "colour": "GREEN"}},
        }


_BALANCE = _load_balancing_data()

# --- EXPORTS (Used by Scheduler & UI) --------------------------------------
ACTION_COSTS: Dict[str, int] = _BALANCE.get("fatigue_costs", {})
ACTION_METADATA: Dict[str, Dict[str, str]] = _BALANCE.get("action_metadata", {})

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
