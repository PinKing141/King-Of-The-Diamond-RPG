"""Physical geometry and surface properties for match venues.

Measurements are in meters to keep physics grounded; callers can convert to
feet when needed for legacy simulations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class StadiumPhysics:
    name: str

    # --- DIMENSIONS (Meters) ---
    distance_left: float      # Distance down the LF line
    distance_center: float    # Distance to dead center
    distance_right: float     # Distance down the RF line

    # "Alley" depth affects doubles/triples
    distance_left_center: float
    distance_right_center: float

    fence_height_left: float  # In meters
    fence_height_center: float
    fence_height_right: float

    foul_ground_size: float   # 1.0 = Standard, 1.5 = Huge (Koshien), 0.5 = Tight

    # --- SURFACE PHYSICS ---
    surface_type: str         # "Black Soil", "Clay", "Turf", "Grass"
    bounce_restitution: float # 1.0 = Standard. Higher = bouncier.
    friction: float           # 1.0 = Standard. Higher = slower rollers.
    bad_hop_chance: float     # 0.0 to 1.0

    # --- ATMOSPHERICS ---
    wind_tunnel_effect: str = "None"  # "Jet Stream", "Swirling", "None"


# --- DEFINITIONS ---

KOSHIEN_STADIUM = StadiumPhysics(
    name="Hanshin Koshien Stadium",
    distance_left=95.0,
    distance_center=118.0,
    distance_right=95.0,
    distance_left_center=118.0,
    distance_right_center=118.0,
    fence_height_left=2.6,
    fence_height_center=2.6,
    fence_height_right=2.6,
    foul_ground_size=1.8,
    surface_type="Black Soil",
    bounce_restitution=0.95,
    friction=1.1,
    bad_hop_chance=0.02,
    wind_tunnel_effect="Hamikaze",
)

TOKYO_DOME_STYLE = StadiumPhysics(
    name="Tokyo Dome Style",
    distance_left=100.0,
    distance_center=122.0,
    distance_right=100.0,
    distance_left_center=110.0,
    distance_right_center=110.0,
    fence_height_left=4.0,
    fence_height_center=4.0,
    fence_height_right=4.0,
    foul_ground_size=0.6,
    surface_type="Artificial Turf",
    bounce_restitution=1.25,
    friction=0.85,
    bad_hop_chance=0.005,
    wind_tunnel_effect="None",
)

MUNICIPAL_FIELD = StadiumPhysics(
    name="Local Municipal Field",
    distance_left=91.0,
    distance_center=110.0,
    distance_right=91.0,
    distance_left_center=105.0,
    distance_right_center=105.0,
    fence_height_left=2.0,
    fence_height_center=2.0,
    fence_height_right=2.0,
    foul_ground_size=1.0,
    surface_type="Rough Clay",
    bounce_restitution=1.0,
    friction=1.2,
    bad_hop_chance=0.12,
)

STADIUM_CATALOG: Dict[str, StadiumPhysics] = {
    "Koshien": KOSHIEN_STADIUM,
    "Dome": TOKYO_DOME_STYLE,
    "Municipal": MUNICIPAL_FIELD,
}


def get_stadium(name: str | None) -> StadiumPhysics:
    if name is None:
        return MUNICIPAL_FIELD
    return STADIUM_CATALOG.get(name, MUNICIPAL_FIELD)
