from __future__ import annotations

from typing import Optional, Protocol


class PlayerLike(Protocol):
    """Shared contract for players participating in the engine."""

    id: int
    name: str
    last_name: str

    # Team identity/handedness (optionals keep the protocol flexible across sources)
    team_id: Optional[int]
    school_id: Optional[int]
    bat_hand: Optional[str]
    bats: Optional[str]
    throws: Optional[str]
    pitch_hand: Optional[str]

    # Role/position metadata
    position: Optional[str]
    primary_position: Optional[str]
    role: Optional[str]
    player_role: Optional[str]
    pitcher_role: Optional[str]
    lineup_position: Optional[int]


class PitcherLike(PlayerLike, Protocol):
    jersey_number: int
    height_inches: int
    wingspan: int
    arm_slot: str
    stamina: float
    aggression: float
    go_to_pitch: Optional[str]
    breaking_ball: Optional[float]
    control: Optional[float]
    velocity: Optional[float]
    movement: Optional[float]
    deception: Optional[float]


class BatterLike(PlayerLike, Protocol):
    contact: Optional[float]
    power: Optional[float]
    discipline: Optional[float]
    speed: Optional[float]
    bat_speed: Optional[float]
