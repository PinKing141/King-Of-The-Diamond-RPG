from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from game.rng import get_rng


@dataclass(frozen=True)
class ArchetypeProfile:
    key: str
    label: str
    description: str
    stat_mods: Dict[str, int]
    tags: Sequence[str] = field(default_factory=tuple)
    weight: float = 1.0
    focus_bias: Dict[str, float] = field(default_factory=dict)
    position_bias: Dict[str, float] = field(default_factory=dict)
    affinity: Dict[str, int] = field(default_factory=dict)


DEFAULT_ARCHETYPE = "steady"

ARCHETYPE_LIBRARY: Dict[str, ArchetypeProfile] = {
    "steady": ArchetypeProfile(
        key="steady",
        label="Steady Anchor",
        description="Calm competitors who steady the locker room and rarely ride emotional rollercoasters.",
        stat_mods={"loyalty": 5, "volatility": -8, "mental": 4, "discipline": 2},
        tags=("stoic", "consistent"),
        weight=1.0,
        focus_bias={"balanced": 1.2, "defense": 1.1},
        position_bias={"infielder": 1.1, "pitcher": 1.05},
        affinity={"loyalty": 60, "volatility": -45},
    ),
    "firebrand": ArchetypeProfile(
        key="firebrand",
        label="Firebrand",
        description="Hypercompetitive sparkplugs who feed on adrenaline and can ignite (or scorch) morale.",
        stat_mods={"drive": 4, "clutch": 5, "volatility": 10, "discipline": -3},
        tags=("emotional", "streaky"),
        weight=0.9,
        focus_bias={"power": 1.3, "guts": 1.25, "gamblers": 1.2},
        position_bias={"outfielder": 1.1, "pitcher": 1.05},
        affinity={"drive": 60, "volatility": 60},
    ),
    "strategist": ArchetypeProfile(
        key="strategist",
        label="Field Strategist",
        description="Film-room junkies who lean on prep, reads, and surgical execution over raw chaos.",
        stat_mods={"discipline": 6, "mental": 6, "clutch": 2, "power": -3},
        tags=("cerebral", "planner"),
        weight=0.85,
        focus_bias={"technical": 1.25, "balanced": 1.1},
        position_bias={"catcher": 1.25, "infielder": 1.1},
        affinity={"discipline": 60, "mental": 60, "volatility": -40},
    ),
    "showman": ArchetypeProfile(
        key="showman",
        label="Showman",
        description="Spotlight seekers who thrive on dramatic swings and crave big-stage moments.",
        stat_mods={"power": 6, "clutch": 6, "loyalty": -4, "volatility": 4},
        tags=("flashy", "crowd-pleaser"),
        weight=0.75,
        focus_bias={"power": 1.3, "random": 1.15},
        position_bias={"outfielder": 1.15, "corner": 1.1},
        affinity={"power": 60, "clutch": 60},
    ),
    "guardian": ArchetypeProfile(
        key="guardian",
        label="Guardian",
        description="Culture keepers who protect younger teammates and keep the battery/tactics aligned.",
        stat_mods={"loyalty": 8, "discipline": 3, "trust_baseline": 5, "power": -2},
        tags=("captain", "mentor"),
        weight=0.8,
        focus_bias={"defense": 1.25, "battery": 1.4},
        position_bias={"catcher": 1.3, "infielder": 1.1},
        affinity={"loyalty": 65, "drive": 55},
    ),
    "sparkplug": ArchetypeProfile(
        key="sparkplug",
        label="Sparkplug",
        description="High-motor hustlers whose energy bleeds into baserunning pressure and chaotic innings.",
        stat_mods={"speed": 6, "drive": 4, "volatility": 4, "mental": 1},
        tags=("energetic", "scrappy"),
        weight=0.85,
        focus_bias={"balanced": 1.1, "small_ball": 1.3},
        position_bias={"outfielder": 1.1, "infielder": 1.05},
        affinity={"speed": 65, "drive": 55},
    ),
}


def list_archetype_profiles() -> List[ArchetypeProfile]:
    return list(ARCHETYPE_LIBRARY.values())


def get_archetype_profile(key: Optional[str]) -> ArchetypeProfile:
    return ARCHETYPE_LIBRARY.get((key or DEFAULT_ARCHETYPE).lower(), ARCHETYPE_LIBRARY[DEFAULT_ARCHETYPE])


def get_player_archetype(player) -> str:
    key = getattr(player, "archetype", None)
    if not key:
        return DEFAULT_ARCHETYPE
    return key.lower()


def assign_player_archetype(player, school=None, position: Optional[str] = None, rng=None) -> ArchetypeProfile:
    key = _pick_archetype_key(player, school, position, rng=rng)
    profile = get_archetype_profile(key)
    _apply_stat_mods(player, profile.stat_mods)
    setattr(player, "archetype", profile.key)
    return profile


def _pick_archetype_key(player, school=None, position: Optional[str] = None, rng=None) -> str:
    rng = rng or get_rng()
    focus = ((getattr(school, "focus", None) or "").lower()) if school else ""
    pos_keys = _position_keys(position or getattr(player, "position", ""))
    drive = getattr(player, "drive", 50) or 50
    loyalty = getattr(player, "loyalty", 50) or 50
    volatility = getattr(player, "volatility", 50) or 50
    discipline = getattr(player, "discipline", 50) or 50
    speed = getattr(player, "speed", 50) or 50
    power = getattr(player, "power", 50) or getattr(player, "velocity", 50) or 50

    base_attrs = {
        "drive": drive,
        "loyalty": loyalty,
        "volatility": volatility,
        "discipline": discipline,
        "speed": speed,
        "power": power,
        "mental": getattr(player, "mental", 50) or 50,
        "clutch": getattr(player, "clutch", 50) or 50,
    }

    weights = []
    keys = []
    for key, profile in ARCHETYPE_LIBRARY.items():
        weight = profile.weight
        if focus:
            weight *= profile.focus_bias.get(focus, 1.0)
        for pk in pos_keys:
            weight *= profile.position_bias.get(pk, 1.0)
        for attr, threshold in profile.affinity.items():
            stat_val = base_attrs.get(attr, getattr(player, attr, 50) or 50)
            if threshold >= 0:
                if stat_val >= threshold:
                    weight *= 1.3
            else:
                if stat_val <= abs(threshold):
                    weight *= 1.3
        if weight <= 0:
            continue
        keys.append(key)
        weights.append(weight)

    if not keys:
        return DEFAULT_ARCHETYPE
    return rng.choices(keys, weights=weights, k=1)[0]


def _position_keys(position: str) -> List[str]:
    pos = (position or "").lower()
    keys = {pos} if pos else set()
    if pos in {"lf", "cf", "rf", "outfielder"}:
        keys.add("outfielder")
    if pos in {"ss", "2b", "3b", "1b", "infielder", "utility"}:
        keys.add("infielder")
    if pos in {"1b", "3b"}:
        keys.add("corner")
    if pos == "catcher":
        keys.add("catcher")
    if pos == "pitcher":
        keys.add("pitcher")
    return list(keys) if keys else ["general"]


def _apply_stat_mods(player, mods: Dict[str, int]) -> None:
    for attr, delta in mods.items():
        if not hasattr(player, attr):
            continue
        current = getattr(player, attr, 0) or 0
        low, high = _stat_bounds(attr)
        new_value = max(low, min(high, int(round(current + delta))))
        setattr(player, attr, new_value)


def _stat_bounds(attr: str) -> Sequence[int]:
    mental_attrs = {"drive", "loyalty", "volatility", "clutch", "discipline", "mental", "trust_baseline"}
    if attr in mental_attrs:
        return 20, 99
    return 1, 99


def archetype_tags(key: Optional[str]) -> Sequence[str]:
    return get_archetype_profile(key).tags


def describe_archetype(key: Optional[str]) -> str:
    profile = get_archetype_profile(key)
    return f"{profile.label}: {profile.description}"


def archetype_persona_blurb(player) -> Optional[str]:
    if player is None:
        return None
    profile = get_archetype_profile(get_player_archetype(player))
    tag_text = ", ".join(profile.tags[:2]) if profile.tags else "balanced"
    return f"Persona — {profile.label} ({tag_text}): {profile.description}"
