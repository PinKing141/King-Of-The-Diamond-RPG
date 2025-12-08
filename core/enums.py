from __future__ import annotations

from enum import Enum


class StatType(str, Enum):
    DRIVE = "drive"
    LOYALTY = "loyalty"
    VOLATILITY = "volatility"
    MENTAL = "mental"
    DISCIPLINE = "discipline"
    CLUTCH = "clutch"
    POWER = "power"
    TRUST_BASELINE = "trust_baseline"
    SPEED = "speed"
    CONTROL = "control"
    VELOCITY = "velocity"
    STAMINA = "stamina"
    ACCURACY = "accuracy"
    ACADEMICS = "academic_skill"


__all__ = ["StatType"]