"""Pitch arsenal reference data for the talent tree and physics overlays.

The lists defined here are intentionally data-only so future systems
(coach scouting, UI displays, AI planners) can consume consistent
requirements, flavour text, and raw movement/velocity numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class PitchDefinition:
    key: str
    name: str
    tier: int
    description: str
    unlock_stats: Dict[str, int]
    unlock_metrics: Dict[str, int]
    tags: List[str]
    velocity_base: float
    break_vertical: float
    break_horizontal: float
    stamina_cost: int
    control_difficulty: float


def _build_pitch(
    *,
    key: str,
    name: str,
    tier: int,
    description: str,
    unlock_stats: Dict[str, int],
    unlock_metrics: Dict[str, int],
    tags: List[str],
    velocity_base: float,
    break_vertical: float,
    break_horizontal: float,
    stamina_cost: int,
    control_difficulty: float,
) -> PitchDefinition:
    return PitchDefinition(
        key=key,
        name=name,
        tier=tier,
        description=description,
        unlock_stats=unlock_stats,
        unlock_metrics=unlock_metrics,
        tags=tags,
        velocity_base=velocity_base,
        break_vertical=break_vertical,
        break_horizontal=break_horizontal,
        stamina_cost=stamina_cost,
        control_difficulty=control_difficulty,
    )


PITCH_DEFINITIONS: Dict[str, PitchDefinition] = {
    "four_seam_fastball": _build_pitch(
        key="four_seam_fastball",
        name="4-Seam Fastball",
        tier=1,
        description="The foundation heater. High velocity with subtle ride.",
        unlock_stats={"velocity": 35, "control": 30},
        unlock_metrics={},
        tags=["fastball", "foundation", "challenge"],
        velocity_base=92.0,
        break_vertical=16.0,
        break_horizontal=0.0,
        stamina_cost=4,
        control_difficulty=1.0,
    ),
    "two_seam_fastball": _build_pitch(
        key="two_seam_fastball",
        name="2-Seam Fastball",
        tier=1,
        description="Arm-side drift that trades a tick of velo for sink.",
        unlock_stats={"movement": 35, "stamina": 35},
        unlock_metrics={},
        tags=["fastball", "movement", "grounder"],
        velocity_base=90.0,
        break_vertical=12.0,
        break_horizontal=-6.0,
        stamina_cost=4,
        control_difficulty=1.1,
    ),
    "changeup": _build_pitch(
        key="changeup",
        name="Circle Change",
        tier=1,
        description="Deceptive speed gap with fading action off the heater.",
        unlock_stats={"control": 40, "stamina": 35},
        unlock_metrics={"feel_for_release": 45},
        tags=["offspeed", "deception"],
        velocity_base=82.0,
        break_vertical=8.0,
        break_horizontal=-8.0,
        stamina_cost=3,
        control_difficulty=1.2,
    ),
    "slider": _build_pitch(
        key="slider",
        name="Slider",
        tier=1,
        description="Tight, late bite. Thrives on spin efficiency.",
        unlock_stats={"movement": 45, "control": 40},
        unlock_metrics={"spin_efficiency": 50},
        tags=["breaking", "putaway"],
        velocity_base=84.0,
        break_vertical=2.0,
        break_horizontal=6.0,
        stamina_cost=5,
        control_difficulty=1.2,
    ),
    "curveball": _build_pitch(
        key="curveball",
        name="12-6 Curve",
        tier=1,
        description="Pure vertical hammer that buckles knees.",
        unlock_stats={"movement": 45, "stamina": 40},
        unlock_metrics={"spin_efficiency": 55},
        tags=["breaking", "vertical"],
        velocity_base=76.0,
        break_vertical=-12.0,
        break_horizontal=0.0,
        stamina_cost=4,
        control_difficulty=1.3,
    ),
    "sinker": _build_pitch(
        key="sinker",
        name="Sinker",
        tier=2,
        description="Bowling-ball drop that lives on weak contact.",
        unlock_stats={"movement": 48, "stamina": 45},
        unlock_metrics={},
        tags=["fastball", "grounder"],
        velocity_base=91.0,
        break_vertical=4.0,
        break_horizontal=-9.0,
        stamina_cost=5,
        control_difficulty=1.3,
    ),
    "cutter_custom": _build_pitch(
        key="cutter_custom",
        name="Cutter",
        tier=2,
        description="Fastball intent with late glove-side chew.",
        unlock_stats={"velocity": 52, "control": 48},
        unlock_metrics={"spin_efficiency": 55},
        tags=["fastball", "late_movement"],
        velocity_base=89.0,
        break_vertical=14.0,
        break_horizontal=3.0,
        stamina_cost=5,
        control_difficulty=1.1,
    ),
    "splitter": _build_pitch(
        key="splitter",
        name="Splitter",
        tier=2,
        description="Fastball window that falls off the table late.",
        unlock_stats={"control": 55, "stamina": 52},
        unlock_metrics={"grip_strength": 60, "finger_length": 50},
        tags=["offspeed", "chase"],
        velocity_base=85.0,
        break_vertical=-4.0,
        break_horizontal=0.0,
        stamina_cost=6,
        control_difficulty=1.6,
    ),
    "sweeper": _build_pitch(
        key="sweeper",
        name="Sweeper",
        tier=3,
        description="Modern breaking ball with massive horizontal glide.",
        unlock_stats={"movement": 60, "control": 50},
        unlock_metrics={"spin_efficiency": 65},
        tags=["breaking", "sweeper", "signature"],
        velocity_base=81.0,
        break_vertical=0.0,
        break_horizontal=18.0,
        stamina_cost=7,
        control_difficulty=1.8,
    ),
    "gyro_slider": _build_pitch(
        key="gyro_slider",
        name="Gyro Slider",
        tier=3,
        description="Bullet-spin breaker that stays on-plane until late.",
        unlock_stats={"movement": 58, "control": 55},
        unlock_metrics={"spin_axis": 60},
        tags=["breaking", "bullet", "signature"],
        velocity_base=86.0,
        break_vertical=0.0,
        break_horizontal=0.0,
        stamina_cost=6,
        control_difficulty=1.5,
    ),
    "vulcan_change": _build_pitch(
        key="vulcan_change",
        name="Vulcan Change",
        tier=3,
        description="Violent fade that only true feel monsters can harness.",
        unlock_stats={"control": 60, "stamina": 55},
        unlock_metrics={"finger_length": 60},
        tags=["offspeed", "signature"],
        velocity_base=80.0,
        break_vertical=-2.0,
        break_horizontal=-10.0,
        stamina_cost=6,
        control_difficulty=1.7,
    ),
    "knuckleball": _build_pitch(
        key="knuckleball",
        name="Knuckleball",
        tier=3,
        description="Chaos pitch that floats until gravity decides otherwise.",
        unlock_stats={"movement": 55, "determination": 60},
        unlock_metrics={"feel_for_release": 65},
        tags=["signature", "wildcard"],
        velocity_base=68.0,
        break_vertical=-1.0,
        break_horizontal=1.0,
        stamina_cost=4,
        control_difficulty=2.0,
    ),
}


PITCH_ALIASES: Dict[str, str] = {
    "4-seam": "four_seam_fastball",
    "4-seam fastball": "four_seam_fastball",
    "four seam": "four_seam_fastball",
    "four seam fastball": "four_seam_fastball",
    "fourseam": "four_seam_fastball",
    "2-seam": "two_seam_fastball",
    "two seam": "two_seam_fastball",
    "two-seam": "two_seam_fastball",
    "two seam fastball": "two_seam_fastball",
    "changeup": "changeup",
    "circle change": "changeup",
    "slider": "slider",
    "curve": "curveball",
    "curveball": "curveball",
    "12-6": "curveball",
    "sinker": "sinker",
    "cutter": "cutter_custom",
    "splitter": "splitter",
    "sweeper": "sweeper",
    "gyro": "gyro_slider",
    "gyro slider": "gyro_slider",
    "vulcan": "vulcan_change",
    "vulcan change": "vulcan_change",
    "knuckle": "knuckleball",
    "knuckleball": "knuckleball",
}


def list_pitches_by_tier(tier: int) -> List[PitchDefinition]:
    """Return all pitch definitions that match the requested tier."""
    return [pitch for pitch in PITCH_DEFINITIONS.values() if pitch.tier == tier]


def resolve_pitch_key(key_or_alias: Optional[str]) -> str:
    """Normalize user-friendly pitch names to canonical keys."""
    if not key_or_alias:
        return "four_seam_fastball"
    lowered = key_or_alias.strip().lower()
    candidate = PITCH_ALIASES.get(lowered, key_or_alias)
    if candidate not in PITCH_DEFINITIONS:
        raise KeyError(f"Unknown pitch: {key_or_alias}")
    return candidate


def get_pitch_definition(key_or_alias: Optional[str]) -> PitchDefinition:
    """Fetch a pitch definition, accepting either a key or alias."""
    return PITCH_DEFINITIONS[resolve_pitch_key(key_or_alias)]


@dataclass(frozen=True)
class LayoutSlot:
    pitch_key: str
    position: Tuple[float, float]
    label_hint: str = ""


@dataclass(frozen=True)
class PitchLayout:
    key: str
    name: str
    description: str
    slots: List[LayoutSlot]
    notes: List[str]


LAYOUT_DEFINITIONS: Dict[str, PitchLayout] = {
    "stellar_arc": PitchLayout(
        key="stellar_arc",
        name="Stellar Arc",
        description="Radial constellation where the heater anchors the dome and signatures orbit outward.",
        slots=[
            LayoutSlot("four_seam_fastball", (0.5, 0.05), "Core Anchor"),
            LayoutSlot("two_seam_fastball", (0.22, 0.23), "Arm-Side Drift"),
            LayoutSlot("changeup", (0.78, 0.24), "Deception"),
            LayoutSlot("slider", (0.16, 0.55), "Glove-Side Bite"),
            LayoutSlot("curveball", (0.84, 0.55), "Vertical Hammer"),
            LayoutSlot("sinker", (0.33, 0.72), "Heavy Sink"),
            LayoutSlot("cutter_custom", (0.5, 0.82), "Late Life"),
            LayoutSlot("splitter", (0.68, 0.88), "Chase Pitch"),
            LayoutSlot("sweeper", (0.12, 0.86), "Mega Sweep"),
        ],
        notes=[
            "Place HUD badges along the arc to highlight opposing movement profiles.",
            "Use subtle star-trail particles to reinforce the constellation vibe.",
        ],
    ),
    "ascension_stair": PitchLayout(
        key="ascension_stair",
        name="Ascension Stair",
        description="Tiered ladder that showcases progression pressure from foundational to mastery tiers.",
        slots=[
            LayoutSlot("four_seam_fastball", (0.1, 0.15), "Baseline"),
            LayoutSlot("two_seam_fastball", (0.3, 0.3), "Sink"),
            LayoutSlot("changeup", (0.5, 0.45), "Tempo Break"),
            LayoutSlot("slider", (0.65, 0.5), "Finish"),
            LayoutSlot("curveball", (0.8, 0.6), "Show Pitch"),
            LayoutSlot("sinker", (0.45, 0.7), "Ground Game"),
            LayoutSlot("cutter_custom", (0.6, 0.78), "Signature Cut"),
            LayoutSlot("splitter", (0.75, 0.82), "Chase Drop"),
            LayoutSlot("sweeper", (0.58, 0.9), "Elite Sweep"),
            LayoutSlot("gyro_slider", (0.78, 0.92), "Gyro Ace"),
            LayoutSlot("vulcan_change", (0.9, 0.95), "Vulcan Fade"),
        ],
        notes=[
            "Great for scrollable mobile cards—each stair can have its own tooltip island.",
            "Highlight unlocked tiers by animating a light sweep up the ladder.",
        ],
    ),
    "signature_triangle": PitchLayout(
        key="signature_triangle",
        name="Signature Triangle",
        description="Hero layout that foregrounds custom creations while grounding with reliable speed/movement pairs.",
        slots=[
            LayoutSlot("four_seam_fastball", (0.5, 0.1), "Launch"),
            LayoutSlot("slider", (0.2, 0.55), "Glove-Side"),
            LayoutSlot("changeup", (0.8, 0.55), "Tempo"),
            LayoutSlot("sinker", (0.15, 0.62), "Bowling Ball"),
            LayoutSlot("cutter_custom", (0.35, 0.72), "Late Steel"),
            LayoutSlot("splitter", (0.65, 0.72), "Gravity Well"),
            LayoutSlot("sweeper", (0.25, 0.85), "Glide"),
            LayoutSlot("gyro_slider", (0.75, 0.85), "Bullet"),
            LayoutSlot("vulcan_change", (0.5, 0.92), "Chaos Pedestal"),
        ],
        notes=[
            "Ideal for story moments—drop a crest or school emblem in the center of the triangle.",
            "Animate connecting lines as the player unlocks each corner to emphasize synergy bonuses.",
        ],
    ),
}


def list_pitch_layouts() -> List[PitchLayout]:
    """Return every curated layout template for UI builders."""
    return list(LAYOUT_DEFINITIONS.values())


def get_pitch_layout(layout_key: str) -> PitchLayout:
    """Lookup helper that raises a KeyError when the layout is unknown."""
    return LAYOUT_DEFINITIONS[layout_key]


def layout_slots_for(layout_key: str) -> List[LayoutSlot]:
    """Convenience method for rendering engines that only need slot metadata."""
    return get_pitch_layout(layout_key).slots
