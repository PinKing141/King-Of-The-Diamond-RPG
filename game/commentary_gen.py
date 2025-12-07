"""Procedural commentary generator that mixes templates with physics tags.

This keeps the logic lightweight while enabling thousands of unique lines via
small, expandable word pools.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from game import commentary_pools as pools
from game.rng import get_rng

rng = get_rng()

_BREAKING_FAMILIES = {"breaker", "curve", "slider", "slurve", "sweeper", "changeup", "splitter", "forkball"}
_FASTBALL_HINTS = {"4-seam", "4 seam", "fastball", "heater", "2-seam", "sinker", "cutter"}


def _safe_name(obj: Any, default: str) -> str:
    if obj is None:
        return default
    if isinstance(obj, str):
        return obj
    name = getattr(obj, "last_name", None) or getattr(obj, "name", None)
    return name or default


def _is_breaking_pitch(pitch_name: str, family: str) -> bool:
    name = (pitch_name or "").lower()
    fam = (family or "").lower()
    if fam and any(tag in fam for tag in _BREAKING_FAMILIES):
        return True
    return any(tag in name for tag in _BREAKING_FAMILIES)


def _is_fastball(pitch_name: str, family: str) -> bool:
    name = (pitch_name or "").lower()
    fam = (family or "").lower()
    if fam and any(tag in fam for tag in _FASTBALL_HINTS):
        return True
    return any(tag in name for tag in _FASTBALL_HINTS)


def _location_tag(raw_loc: Optional[str]) -> str:
    loc = (raw_loc or "").lower()
    if loc in {"zone", "in"}:
        return "on the black"
    if loc in {"chase", "out"}:
        return "off the plate"
    if "up" in loc:
        return "upstairs"
    if "down" in loc:
        return "at the knees"
    return rng.choice(pools.LOCATION_TAGS)


def generate_pitch_commentary(pitcher: Any, batter: Any, pitch_data: Dict[str, Any]) -> Optional[str]:
    """Return a single commentary line or None if nothing fits.

    Expected pitch_data keys (best-effort): velocity (kph), pitch_name,
    pitch_family, result ("strikeout", etc.), location.
    """

    if not pitch_data:
        return None

    velo = float(pitch_data.get("velocity") or 0.0)
    pitch_name = pitch_data.get("pitch_name") or pitch_data.get("type") or "Pitch"
    pitch_family = pitch_data.get("pitch_family") or ""
    location = _location_tag(pitch_data.get("location"))
    result = str(pitch_data.get("result") or "").lower()
    exit_velo = float(pitch_data.get("exit_velocity") or 0.0)
    launch_angle = float(pitch_data.get("launch_angle") or 0.0)
    distance = float(pitch_data.get("distance") or 0.0)
    contact_sound = rng.choice(pools.CONTACT_SOUNDS)

    pitcher_name = _safe_name(pitcher, "Pitcher")
    batter_name = _safe_name(batter, "Batter")

    is_high_heat = velo >= 150
    is_breaker = _is_breaking_pitch(pitch_name, pitch_family)
    is_fastball = _is_fastball(pitch_name, pitch_family)

    context = {
        "pitcher": pitcher_name,
        "batter": batter_name,
        "velocity": f"{int(round(velo))} kph" if velo else "high heat",
        "pitch_name": pitch_name,
        "location": location,
        "velo_verb": rng.choice(pools.VELOCITY_VERBS),
        "velo_adj": rng.choice(pools.VELOCITY_ADJECTIVES),
        "break_verb": rng.choice(pools.BREAKING_VERBS),
        "exit_velo": f"{int(round(exit_velo))} kph" if exit_velo else "",
        "launch_angle": int(round(launch_angle)) if launch_angle else 0,
        "distance": int(round(distance)) if distance else 0,
        "contact_sound": contact_sound,
    }

    templates = []
    if "strikeout" in result or result == "k":
        if is_high_heat and is_fastball:
            templates = pools.STRIKEOUT_HIGH_HEAT
        elif is_breaker:
            templates = pools.STRIKEOUT_BREAKING
        else:
            templates = pools.STRIKEOUT_FINESSE
    elif result == "inplay":
        # Use physics if available; otherwise generic contact line.
        physics_rich = exit_velo and launch_angle
        if physics_rich:
            templates = pools.CONTACT_OUTCOMES
        else:
            templates = ["{batter} puts it in play against a {pitch_name}."]
    elif result == "blocked_pitch":
        templates = pools.BLOCK_TEMPLATES

    if not templates:
        templates = pools.STRIKEOUT_GENERIC if result else []
    if not templates:
        return None

    return rng.choice(templates).format(**context)


__all__ = ["generate_pitch_commentary"]
