"""
Physical geometry and surface properties for match venues.

These profiles mirror common Japanese high school environments and are used by
ball_in_play.py (trajectory / fence checks) and fielding_engine.py (grounder physics).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class StadiumPhysics:
    name: str
    description: str

    # --- GEOMETRY (Meters) ---
    distance_left: float
    distance_left_center: float
    distance_center: float
    distance_right_center: float
    distance_right: float

    fence_height_left: float
    fence_height_center: float
    fence_height_right: float

    # 1.0 = standard foul space. >1.0 = huge, <1.0 = tight.
    foul_ground_scale: float

    # --- SURFACE PHYSICS ---
    surface_type: str
    restitution: float          # Bounciness
    friction: float             # Ground speed
    bad_hop_chance: float       # Probability of a bad hop on grounders
    bounce_restitution: Optional[float] = None  # Alias for callers expecting this field

    # --- ATMOSPHERICS ---
    wind_profile: str = "None"


# ---------------------------------------------------------------------------
# 1. THE HOLY GROUND: HANSHIN KOSHIEN STADIUM
# ---------------------------------------------------------------------------
KOSHIEN_STADIUM = StadiumPhysics(
    name="Hanshin Koshien Stadium",
    description="The sacred soil. A massive infield and deep alleys test true power.",
    distance_left=95.0,
    distance_left_center=118.0,
    distance_center=118.0,
    distance_right_center=118.0,
    distance_right=95.0,
    fence_height_left=2.6,
    fence_height_center=2.6,
    fence_height_right=2.6,
    foul_ground_scale=1.8,
    surface_type="Black Soil",
    restitution=0.95,
    friction=1.05,
    bad_hop_chance=0.02,
    bounce_restitution=0.95,
    wind_profile="Hamikaze",
)


# ---------------------------------------------------------------------------
# 2. BIG SCHOOL STANDARD: PREFECTURAL / DOME STYLE
# ---------------------------------------------------------------------------
BIG_SCHOOL_STADIUM = StadiumPhysics(
    name="Prefectural Stadium (Turf)",
    description="A modern pro-style venue. Fast turf rewards speed and gap hitters.",
    distance_left=100.0,
    distance_left_center=116.0,
    distance_center=122.0,
    distance_right_center=116.0,
    distance_right=100.0,
    fence_height_left=4.0,
    fence_height_center=4.0,
    fence_height_right=4.0,
    foul_ground_scale=0.6,
    surface_type="Artificial Turf",
    restitution=1.25,
    friction=0.85,
    bad_hop_chance=0.005,
    bounce_restitution=1.25,
    wind_profile="None",
)


# ---------------------------------------------------------------------------
# 3. SMALL SCHOOL STANDARD: MUNICIPAL RIVERBANK FIELD
# ---------------------------------------------------------------------------
SMALL_SCHOOL_STADIUM = StadiumPhysics(
    name="Municipal Field",
    description="Cramped dimensions and rough clay. Anything can happen here.",
    distance_left=91.0,
    distance_left_center=105.0,
    distance_center=110.0,
    distance_right_center=105.0,
    distance_right=91.0,
    fence_height_left=2.0,
    fence_height_center=2.5,
    fence_height_right=2.0,
    foul_ground_scale=1.0,
    surface_type="Rough Clay",
    restitution=1.0,
    friction=1.2,
    bad_hop_chance=0.15,
    bounce_restitution=1.0,
    wind_profile="Swirling",
)

# Aliases for engine callers
PREFECTURAL_STADIUM = BIG_SCHOOL_STADIUM
MUNICIPAL_FIELD = SMALL_SCHOOL_STADIUM


# --- ACCESSOR ---
STADIUM_CATALOG: Dict[str, StadiumPhysics] = {
    "Koshien": KOSHIEN_STADIUM,
    "Big": BIG_SCHOOL_STADIUM,
    "Small": SMALL_SCHOOL_STADIUM,
    "Standard": BIG_SCHOOL_STADIUM,
}


def get_stadium(key: Optional[str]) -> StadiumPhysics:
    """Retrieve stadium by key, defaulting to Big School if unknown."""
    if key is None:
        return BIG_SCHOOL_STADIUM
    lowered = key.lower()
    if "koshien" in lowered:
        return KOSHIEN_STADIUM
    if "municipal" in lowered or "small" in lowered:
        return SMALL_SCHOOL_STADIUM
    return STADIUM_CATALOG.get(key, BIG_SCHOOL_STADIUM)
