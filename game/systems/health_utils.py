"""
Utility helpers to convert internal health/load metrics into player-friendly labels.
"""
from __future__ import annotations

from typing import Tuple


def get_stamina_status(current_stamina: float) -> Tuple[str, str]:
    """Return (label, colour_code) for stamina buckets."""
    if current_stamina > 80:
        return "Fresh", "green"
    if current_stamina > 50:
        return "Normal", "white"
    if current_stamina > 20:
        return "Tired", "yellow"
    return "DANGER", "red"


def get_fatigue_status(fatigue: float) -> str:
    """Translate fatigue percentage into plain-language risk."""
    if fatigue < 20:
        return "Low Risk"
    if fatigue < 50:
        return "Accumulating"
    if fatigue < 80:
        return "High Risk"
    return "CRITICAL"


def get_training_load_label(load_value: str) -> str:
    """Map internal load tags to descriptive text."""
    labels = {
        "LIGHT": "Light (Recovery)",
        "MEDIUM": "Standard",
        "HEAVY": "Intense",
        "EDGE": "Overload (Risk!)",
    }
    return labels.get(load_value, "Unknown")
