"""Deterministic(ish) fielding simulation helpers.

The engine accepts simple batted-ball parameters (exit velocity, launch angle,
spray angle) and a snapshot of the defensive alignment.  It estimates where the
ball will land, how long it will stay in the air, whether a defender can get
there in time, and whether the follow-up throw beats the runner.  Reliability
rolls still introduce chaos, but the geometry is now grounded in one cohesive
place so other systems can introspect or extend it later.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from game.rng import get_rng
from world.defense_profiles import DefenseProfile, DEFAULT_PROFILE, get_defense_profile

GRAVITY_FTPS2 = 32.174
MPH_TO_FTPS = 1.46667
FENCE_DISTANCE_FT = 330.0
AIR_RESISTANCE_FACTOR = 1.58  # Softens perfect-physics distance so 95 mph flies stay in the park
DEFAULT_INFIELD_GROUND_SPEED = 95.0  # ft/s once the ball is on the dirt
FIRST_BASE_COORD = (63.5, 63.5)

INFIELD_POSITIONS = {
    "pitcher",
    "catcher",
    "first base",
    "second base",
    "shortstop",
    "third base",
}
OUTFIELD_POSITIONS = {"left field", "center field", "right field"}

_rng = get_rng()

__all__ = [
    "BattedBall",
    "FielderSnapshot",
    "FieldingPlayResult",
    "simulate_batted_ball",
    "build_defense_alignment",
    "resolve_fielding_play",
]


@dataclass
class BattedBall:
    exit_velocity: float
    launch_angle: float
    spray_angle: float
    hang_time: float
    landing_distance: float
    landing_x: float
    landing_y: float
    apex_height: float
    ground_time: float
    ball_type: str
    is_home_run: bool


@dataclass
class FielderSnapshot:
    player: object | None
    position: str
    x: float
    y: float
    speed_rating: float
    reaction_rating: float
    reliability_rating: float
    arm_rating: float

    @property
    def label(self) -> str:
        player = self.player
        if player:
            return getattr(player, "last_name", None) or getattr(player, "name", None) or self.position
        return self.position


@dataclass
class FieldingPlayResult:
    hit_type: str
    description: str
    primary_position: Optional[str] = None
    error_type: Optional[str] = None  # "E_FIELD" / "E_THROW"
    caught: bool = False
    fielded_clean: bool = False
    throw_completed: bool = False

    @property
    def bases(self) -> int:
        mapping = {"Out": 0, "1B": 1, "2B": 2, "3B": 3, "HR": 4}
        return mapping.get(self.hit_type, 0)


_POSITION_COORDS = {
    "pitcher": (0.0, 57.5),
    "catcher": (0.0, -8.0),
    "first base": (63.5, 63.5),
    "second base": (0.0, 127.0),
    "shortstop": (-35.0, 115.0),
    "third base": (-63.5, 63.5),
    "left field": (-185.0, 215.0),
    "center field": (0.0, 250.0),
    "right field": (185.0, 215.0),
}

_SHIFT_OFFSETS = {
    "double_play": {"second base": (0, -10), "shortstop": (0, -10)},
    "infield_in": {
        "first base": (0, -18),
        "second base": (0, -18),
        "shortstop": (0, -18),
        "third base": (0, -18),
    },
    "deep_outfield": {
        "left field": (0, 20),
        "center field": (0, 20),
        "right field": (0, 20),
    },
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _spray_to_xy(distance: float, spray_angle: float) -> tuple[float, float]:
    rad = math.radians(spray_angle)
    x = distance * math.sin(rad)
    y = distance * math.cos(rad)
    return x, y


def simulate_batted_ball(
    exit_velocity: float,
    launch_angle: float,
    spray_angle: float,
    *,
    fence_distance: float = FENCE_DISTANCE_FT,
) -> BattedBall:
    """Convert simple launch params into a landing coordinate."""

    velocity_fps = exit_velocity * MPH_TO_FTPS
    angle = math.radians(_clamp(launch_angle, -5.0, 75.0))
    vertical = velocity_fps * math.sin(angle)
    horizontal = velocity_fps * math.cos(angle)
    ball_type = "ground" if launch_angle < 10 else ("line" if launch_angle < 25 else "fly")

    if ball_type == "ground":
        hang_time = max(0.18, 0.35 + (launch_angle / 35.0))
        distance = _clamp(100.0 + (exit_velocity - 80.0) * 1.8, 85.0, 170.0)
        travel_time = distance / DEFAULT_INFIELD_GROUND_SPEED
        ground_time = hang_time + travel_time
    else:
        hang_time = max(0.6, (2 * vertical) / GRAVITY_FTPS2)
        raw_distance = (velocity_fps ** 2 * math.sin(2 * angle)) / GRAVITY_FTPS2
        distance = max(70.0, raw_distance / AIR_RESISTANCE_FACTOR)
        ground_time = hang_time  # first touch happens at landing

    landing_x, landing_y = _spray_to_xy(distance, spray_angle)
    is_home_run = ball_type != "ground" and distance >= fence_distance
    apex_height = (vertical ** 2) / (2 * GRAVITY_FTPS2)

    return BattedBall(
        exit_velocity=exit_velocity,
        launch_angle=launch_angle,
        spray_angle=spray_angle,
        hang_time=hang_time,
        landing_distance=distance,
        landing_x=landing_x,
        landing_y=landing_y,
        apex_height=apex_height,
        ground_time=ground_time,
        ball_type=ball_type,
        is_home_run=is_home_run,
    )


def _rating_to_speed_ftps(rating: float, profile: DefenseProfile) -> float:
    base = 20.5 + (rating - 50.0) * 0.22
    return max(14.0, base * profile.range_multiplier)


def _reaction_delay(rating: float, profile: DefenseProfile) -> float:
    delay = 0.38 - (rating - 50.0) * 0.0042
    delay /= max(0.6, profile.range_multiplier)
    return _clamp(delay, 0.06, 0.48)


def _reliability_value(rating: float, profile: DefenseProfile) -> float:
    return _clamp(rating + profile.reliability_bonus, 25.0, 99.0)


def _arm_velocity_fps(rating: float, profile: DefenseProfile) -> float:
    mph = 75.0 + (rating - 50.0) * 0.9 + profile.arm_bonus
    return max(70.0, mph * MPH_TO_FTPS)


def _transfer_time(reliability: float) -> float:
    return _clamp(0.42 - (reliability - 50.0) * 0.0025, 0.18, 0.45)


def _runner_time_to_first(runner_speed: float) -> float:
    return _clamp(4.35 - (runner_speed - 50.0) * 0.022, 3.55, 4.6)


def _bases_from_distance(distance: float) -> str:
    if distance >= 300:
        return "3B"
    if distance >= 240:
        return "2B"
    return "1B"


def _apply_shift_offsets(position: str, shift: str) -> tuple[float, float]:
    offset = _SHIFT_OFFSETS.get(shift, {}).get(position, (0.0, 0.0))
    base = _POSITION_COORDS.get(position, (0.0, 0.0))
    return base[0] + offset[0], base[1] + offset[1]


def build_defense_alignment(state, *, profile: DefenseProfile | None = None) -> list[FielderSnapshot]:
    """Return defender snapshots for the current fielding team."""

    if state is None:
        return []
    defense_team = state.home_team if getattr(state, "top_bottom", "Top") == "Top" else state.away_team
    profile = profile or get_defense_profile(defense_team)
    if getattr(state, "top_bottom", "Top") == "Top":
        roster = getattr(state, "home_roster", None) or getattr(state, "home_lineup", None)
    else:
        roster = getattr(state, "away_roster", None) or getattr(state, "away_lineup", None)
    shift = getattr(state, "defensive_shift", "normal")
    snapshots: list[FielderSnapshot] = []

    if roster:
        for player in roster:
            if not player:
                continue
            position = getattr(player, "position", None)
            if not position:
                continue
            position_key = position.strip().lower()
            if position_key not in _POSITION_COORDS:
                continue
            x, y = _apply_shift_offsets(position_key, shift)
            snapshots.append(
                FielderSnapshot(
                    player=player,
                    position=position,
                    x=x,
                    y=y,
                    speed_rating=getattr(player, "speed", getattr(player, "running", 55)) or 55,
                    reaction_rating=getattr(player, "awareness", getattr(player, "iq", 55)) or 55,
                    reliability_rating=getattr(player, "fielding", 55) or 55,
                    arm_rating=getattr(player, "arm_strength", getattr(player, "power", 55)) or 55,
                )
            )

    # Fill any missing standard positions with anonymous league-average defenders
    for position_key in _POSITION_COORDS:
        if any(s.position.lower() == position_key for s in snapshots):
            continue
        x, y = _apply_shift_offsets(position_key, shift)
        snapshots.append(
            FielderSnapshot(
                player=None,
                position=position_key.title(),
                x=x,
                y=y,
                speed_rating=55,
                reaction_rating=55,
                reliability_rating=55,
                arm_rating=55,
            )
        )

    # Tag profile so downstream callers can reuse it without recomputing.
    for snap in snapshots:
        snap.profile = profile  # type: ignore[attr-defined]
    return snapshots


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _pick_candidate(ball: BattedBall, defenders: Sequence[FielderSnapshot]) -> Optional[FielderSnapshot]:
    if not defenders:
        return None
    eligible_positions = INFIELD_POSITIONS if ball.ball_type == "ground" else INFIELD_POSITIONS | OUTFIELD_POSITIONS
    best = None
    best_dist = float("inf")
    landing = (ball.landing_x, ball.landing_y)
    for snap in defenders:
        if snap.position.lower() not in eligible_positions:
            continue
        dist = _distance((snap.x, snap.y), landing)
        if dist < best_dist:
            best = snap
            best_dist = dist
    return best


def _fielding_error_occurs(reliability: float, *, profile: DefenseProfile, error_rate: float = 1.0) -> bool:
    error_chance = max(0.01, (70.0 - reliability) / 170.0)
    error_chance *= profile.error_rate * error_rate
    return _rng.random() < error_chance


def _bases_for_missed_play(ball: BattedBall) -> str:
    if ball.ball_type == "ground":
        return "1B" if ball.landing_distance < 140 else "2B"
    return _bases_from_distance(ball.landing_distance)


def _throw_time_to_first(fielder: FielderSnapshot, profile: DefenseProfile, stop: tuple[float, float]) -> float:
    arm_speed = _arm_velocity_fps(fielder.arm_rating, profile)
    distance = _distance((fielder.x, fielder.y), stop)
    return distance / arm_speed


def resolve_fielding_play(
    ball: BattedBall,
    defenders: Sequence[FielderSnapshot],
    *,
    runner_speed: float,
    profile: DefenseProfile | None = None,
    environment_error_scalar: float = 1.0,
) -> FieldingPlayResult:
    """Simulate the interaction between the ball and the defense."""

    profile = profile or DEFAULT_PROFILE
    env_error = max(0.5, min(1.8, environment_error_scalar))
    if ball.is_home_run:
        return FieldingPlayResult("HR", "Launched over the wall!", primary_position=None, caught=False)

    fielder = _pick_candidate(ball, defenders)
    if fielder is None:
        hit = _bases_for_missed_play(ball)
        return FieldingPlayResult(hit, "No defender nearby; it rolls forever.")

    reliability = _reliability_value(fielder.reliability_rating, profile)
    range_speed = _rating_to_speed_ftps(fielder.speed_rating, profile)
    reaction = _reaction_delay(fielder.reaction_rating, profile)
    if ball.ball_type == "ground":
        reaction *= 0.7
    landing_point = (ball.landing_x, ball.landing_y)
    distance_to_ball = _distance((fielder.x, fielder.y), landing_point)
    time_to_ball = reaction + distance_to_ball / range_speed
    runner_time = _runner_time_to_first(runner_speed)

    if ball.ball_type in {"fly", "line"}:
        if time_to_ball <= ball.hang_time:
            if _fielding_error_occurs(reliability, profile=profile, error_rate=env_error):
                hit = "1B"
                desc = f"{fielder.label} drops the easy fly!"
                return FieldingPlayResult(
                    hit,
                    desc,
                    primary_position=fielder.position,
                    error_type="E_FIELD",
                    caught=False,
                )
            return FieldingPlayResult(
                "Out",
                f"{fielder.label} camps under it for the out.",
                primary_position=fielder.position,
                caught=True,
                fielded_clean=True,
            )
        hit = _bases_for_missed_play(ball)
        desc = "Drifts into the gap for extra bases." if hit != "1B" else "Falls in front of the outfield for a single."
        return FieldingPlayResult(hit, desc, primary_position=fielder.position)

    # Ground ball branch
    if time_to_ball <= ball.ground_time + 0.2:
        transfer = _transfer_time(reliability)
        throw_time = _throw_time_to_first(fielder, profile, FIRST_BASE_COORD)
        total_defense_time = time_to_ball + transfer + throw_time
        if _fielding_error_occurs(reliability, profile=profile, error_rate=0.9 * env_error):
            return FieldingPlayResult(
                "1B",
                f"{fielder.label} boots it!",
                primary_position=fielder.position,
                error_type="E_FIELD",
            )
        if total_defense_time <= runner_time:
            if _fielding_error_occurs(reliability, profile=profile, error_rate=1.05 * env_error):
                return FieldingPlayResult(
                    "1B",
                    f"Throw pulls the first baseman off the bag!",
                    primary_position=fielder.position,
                    error_type="E_THROW",
                    fielded_clean=True,
                )
            return FieldingPlayResult(
                "Out",
                f"{fielder.label} makes the play and beats him by a step.",
                primary_position=fielder.position,
                fielded_clean=True,
                throw_completed=True,
            )
        desc = "Beats it out for an infield single."
        return FieldingPlayResult("1B", desc, primary_position=fielder.position)

    # Ball got through the infield before anyone could glove it.
    hit = _bases_for_missed_play(ball)
    desc = "Smoked past the infield!" if hit != "1B" else "Grounder sneaks through the hole."
    return FieldingPlayResult(hit, desc, primary_position=fielder.position)
