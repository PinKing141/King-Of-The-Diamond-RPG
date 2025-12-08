"""Unified fielding decision/resolve logic for user and AI fielders.

This is intentionally lightweight so it can sit beside the existing
world_sim.fielding_engine. Use it when you want interactive/user-driven
choices (or AI mirroring the same rules) for a specific fielder.
"""
from __future__ import annotations

from typing import Dict, Optional

from core.io_interface import IOInterface

from database.setup_db import Player
from core.rng import get_rng
from ui.ui_display import Colour

rng = get_rng()

# --- CONFIGURATION SCALARS ---
DIFFICULTY_MODIFIERS = {
    "ROUTINE": 0.8,
    "TOUGH": 1.2,
    "HERO": 1.8,
}


def _stat(player: Player, attr: str, default: float = 50.0) -> float:
    return float(getattr(player, attr, default) or default)


def _defense(player: Player) -> float:
    # Prefer fielding; fall back to defense if present
    return _stat(player, "fielding", _stat(player, "defense", 50.0))


def _arm_accuracy(player: Player) -> float:
    return _defense(player) * 0.6 + _stat(player, "throwing", 0) * 0.6


def _arm_strength(player: Player) -> float:
    return _stat(player, "throwing", _stat(player, "power", 40.0))


def _speed(player: Player) -> float:
    return _stat(player, "speed", 50.0)


def run_fielding_event(
    fielder: Player,
    is_user: bool,
    ball_type: str,  # "GROUNDER", "FLYBALL", "LINE_DRIVE"
    location: str,  # "INFIELD", "OUTFIELD"
    runners: Dict[int, bool],  # {1: bool, 2: bool, 3: bool}
    difficulty: str = "ROUTINE",
    io: Optional[IOInterface] = None,
) -> Dict[str, str]:
    """Run a two-phase fielding resolution (approach -> throw).

    Returns a dict with keys: result_code, narrative
    """
    diff_mod = DIFFICULTY_MODIFIERS.get(difficulty.upper(), 1.0)
    _log(io, f"\n{Colour.CYAN}--- FIELDING EVENT: {getattr(fielder, 'position', '??')} ({getattr(fielder, 'name', 'Player')}) ---{Colour.RESET}")

    approach = _get_approach_decision(fielder, is_user, ball_type, location, io=io)
    catch = _calculate_catch_outcome(fielder, approach, ball_type, location, diff_mod)
    _log(io, f">> {catch['description']}")

    if catch["outcome"] != "SUCCESS":
        code = "ERROR" if "ERROR" in catch["outcome"] else "HIT"
        return {"result_code": code, "narrative": catch["description"]}

    throw_target = _get_throw_decision(fielder, is_user, runners, location, io=io)
    throw = _calculate_throw_outcome(fielder, throw_target, location, diff_mod)
    _log(io, f">> {throw['description']}")

    return {
        "result_code": throw["outcome"],
        "narrative": f"{catch['description']} {throw['description']}",
    }


# -----------------------------------------------------------------------------
# DECISION LAYER
# -----------------------------------------------------------------------------


def _log(io: Optional[IOInterface], message: str) -> None:
    if io:
        io.log(message)
    else:
        print(message)


def _prompt(io: Optional[IOInterface], prompt: str) -> str:
    if io:
        return io.prompt(prompt)
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""


def _get_approach_decision(fielder: Player, is_user: bool, ball_type: str, location: str, *, io: Optional[IOInterface]) -> str:
    if is_user:
        _log(io, f"\n{Colour.WARNING}A {ball_type.lower()} is hit to your {location.lower()}!{Colour.RESET}")
        _log(io, f"Stats: Fld {_defense(fielder):.0f} | Spd {_speed(fielder):.0f}")
        if location.upper() == "INFIELD":
            _log(io, "[1] Square Up (Safe) - Block the ball, prevent errors.")
            _log(io, "[2] Charge/Dive (Aggressive) - Try to cut the runner.")
        else:
            _log(io, "[1] Play Bounce/Safe - Keep ball in front.")
            _log(io, "[2] Dive/Shoestring - Go for the highlight.")
        choice = _prompt(io, "Select Approach: ").strip()
        return "AGGRESSIVE" if choice == "2" else "SAFE"

    # AI path
    aggression_score = rng.uniform(0, 100)
    aggression_score += (_defense(fielder) - 55) * 0.4
    aggression_score += (_speed(fielder) - 55) * 0.2 if location.upper() == "OUTFIELD" else 0
    return "AGGRESSIVE" if aggression_score > 72 else "SAFE"


def _get_throw_decision(
    fielder: Player,
    is_user: bool,
    runners: Dict[int, bool],
    location: str,
    *,
    io: Optional[IOInterface],
) -> str:
    lead_runner_base = 3 if runners.get(3) else (2 if runners.get(2) else 1 if runners.get(1) else 0)
    if is_user:
        _log(io, f"\n{Colour.WARNING}You have the ball!{Colour.RESET}")
        _log(io, "[1] Sure Out (1st / cutoff)")
        if lead_runner_base > 1:
            target = "Home" if lead_runner_base == 3 else "3rd" if lead_runner_base == 2 else "2nd"
            _log(io, f"[2] Get Lead Runner (Throw to {target}) - Higher risk.")
        choice = _prompt(io, "Select Throw: ").strip()
        if choice == "2" and lead_runner_base > 1:
            return "LEAD_RUNNER"
        return "SURE_OUT"

    # AI path
    if location.upper() == "OUTFIELD" and _arm_strength(fielder) < 55:
        return "SURE_OUT"
    if location.upper() == "INFIELD" and lead_runner_base == 1:
        return "LEAD_RUNNER" if rng.random() < 0.4 else "SURE_OUT"
    return "SURE_OUT"


# -----------------------------------------------------------------------------
# CALCULATION LAYER
# -----------------------------------------------------------------------------


def _calculate_catch_outcome(
    fielder: Player,
    approach: str,
    ball_type: str,
    location: str,
    difficulty_mod: float,
) -> Dict[str, str]:
    defense = _defense(fielder)
    speed = _speed(fielder)
    roll = rng.uniform(0, 100)

    threshold = defense
    if location.upper() == "OUTFIELD":
        threshold += (speed - 50) * 0.4
    if approach == "SAFE":
        threshold += 18
        description = f"{getattr(fielder, 'name', 'Fielder')} squares up and smothers it."
        fail_desc = f"{getattr(fielder, 'name', 'Fielder')} misplays it!"
    else:
        threshold -= 8
        threshold += (speed - 50) * 0.35
        description = f"{getattr(fielder, 'name', 'Fielder')} attacks the ball aggressively!"
        fail_desc = f"{getattr(fielder, 'name', 'Fielder')} lays out and misses!"

    threshold /= difficulty_mod

    if roll < threshold:
        return {"outcome": "SUCCESS", "description": description}
    outcome_code = "ERROR_SAFE" if approach == "SAFE" else "ERROR_RISKY"
    return {"outcome": outcome_code, "description": fail_desc}


def _calculate_throw_outcome(
    fielder: Player,
    throw_type: str,
    location: str,
    difficulty_mod: float,
) -> Dict[str, str]:
    arm_acc = _arm_accuracy(fielder)
    arm_str = _arm_strength(fielder)
    roll = rng.uniform(0, 100)

    if throw_type == "SURE_OUT":
        target = arm_acc + 30
        if roll < target / difficulty_mod:
            return {"outcome": "OUT", "description": "Clean throw for the sure out."}
        return {"outcome": "SAFE", "description": "Pulls the first baseman off the bag."}

    if throw_type == "LEAD_RUNNER":
        penalty = 30 if location.upper() == "OUTFIELD" else 10
        target = (arm_acc + arm_str) / 2 - penalty
        if roll < target / difficulty_mod:
            return {"outcome": "OUT", "description": "Laser to cut down the lead runner!"}
        return {"outcome": "SAFE", "description": "Throw is late; runner advances safely."}

    return {"outcome": "SAFE", "description": "No throw made."}
