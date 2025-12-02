"""Shared gameplay configuration for UI + simulation layers."""
from __future__ import annotations

from typing import Dict, Tuple

# --- Action Cost + Metadata -------------------------------------------------
ACTION_COSTS: Dict[str, int] = {
    "rest": -15,
    "team_practice": 20,
    "practice_match": 35,
    "b_team_match": 25,
    "train_heavy": 15,
    "train_light": 10,
    "study": 5,
    "social": 5,
    "mind": 0,
}

HEAVY_TRAINING_ACTIONS = {"train_power", "train_speed", "train_stamina"}
LIGHT_TRAINING_ACTIONS = {"train_control", "train_contact"}

ACTION_METADATA: Dict[str, Dict[str, str]] = {
    "rest": {"short": "REST", "desc": "Recover fatigue and clear the head.", "colour": "GREEN"},
    "team_practice": {"short": "TEAM", "desc": "Mandatory drills with the varsity squad.", "colour": "YELLOW"},
    "practice_match": {"short": "GAME", "desc": "A-team practice game for prestige.", "colour": "RED"},
    "b_team_match": {"short": "SCRM", "desc": "B-team scrimmage to climb the ladder.", "colour": "GOLD"},
    "train_heavy": {"short": "HARD", "desc": "High-intensity strength & power focus.", "colour": "CYAN"},
    "train_light": {"short": "DRIL", "desc": "Technique reps for finesse stats.", "colour": "CYAN"},
    "study": {"short": "STDY", "desc": "Academics time to avoid suspension.", "colour": "BLUE"},
    "social": {"short": "SOCL", "desc": "Team bonding to reduce stress.", "colour": "BLUE"},
    "mind": {"short": "MIND", "desc": "Visualization / focus reset.", "colour": "CYAN"},
}

ACTION_METADATA_DEFAULT = {"short": "????", "desc": "Unassigned slot.", "colour": "RESET"}

# --- Mandatory Schedule Policies --------------------------------------------
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
