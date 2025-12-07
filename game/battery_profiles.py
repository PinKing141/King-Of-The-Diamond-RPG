"""Lightweight battery chemistry analyzer.

Converts pitcher/catcher stat interactions into a simple title/description for UI.
"""
from __future__ import annotations

from typing import Tuple


def _pitcher_type(velo: int, control: int) -> str:
    if velo >= 150 and control <= 50:
        return "Wild"
    if velo >= 148:
        return "Flame"
    if velo <= 135 and control >= 70:
        return "Finesse"
    if control <= 45:
        return "Erratic"
    return "Standard"


def _catcher_type(wall: int, arm: int) -> str:
    if wall >= 80:
        return "Wall"
    if wall <= 45:
        return "Sieve"
    if arm >= 75:
        return "Cannon"
    return "Standard"


def analyze_battery_chemistry(pitcher, catcher, trust_score: int | float = 50) -> Tuple[str, str]:
    velo = int(getattr(pitcher, "velocity", 130) or 130)
    ctrl = int(getattr(pitcher, "control", 50) or 50)
    wall = int(getattr(catcher, "catcher_ability", 50) or 50)
    arm = int(getattr(catcher, "throwing", 50) or 50)

    p_type = _pitcher_type(velo, ctrl)
    c_type = _catcher_type(wall, arm)

    title = "Standard Battery"
    desc = "Balanced pairing with no glaring strengths or weaknesses."

    if p_type == "Wild" and c_type == "Wall":
        title = "Tamed Beast"
        desc = "Wild heat paired with a true wall — strikeouts without the chaos."
    elif p_type == "Wild" and c_type == "Sieve":
        title = "Glass Cannon"
        desc = "Punches out hitters but leaks bases on passed balls and spikes."
    elif p_type == "Flame" and c_type == "Cannon":
        title = "Strikeout/Throwout"
        desc = "Power on the mound and hose behind the plate punish runners."
    elif p_type == "Finesse" and c_type in {"Wall", "Standard"}:
        title = "Frame Artists"
        desc = "Command-first pitcher with a steady mitt steals the edges."
    elif p_type == "Erratic" and c_type == "Wall":
        title = "Safety Net"
        desc = "Erratic command cushioned by elite blocking."

    if trust_score >= 90:
        title = f"Telepathic {title}"
    elif trust_score <= 20:
        title = f"Dysfunctional {title}"

    return title, desc


__all__ = ["analyze_battery_chemistry"]
