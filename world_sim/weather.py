"""Procedural weather generator shared between world sim and match engine."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Sequence

from game.rng import get_rng

WIND_DIRECTIONS: Sequence[str] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


@dataclass
class WeatherEffects:
    ball_slip_chance: float = 0.0
    stamina_drain_scalar: float = 1.0
    ground_ball_speed_bonus: float = 0.0
    fly_ball_distance_delta_m: float = 0.0


@dataclass
class WeatherProfile:
    label: str
    condition: str
    precipitation: str
    temperature_f: int
    wind_speed_mph: float
    wind_direction: str
    carry_modifier: float
    error_modifier: float
    wild_pitch_modifier: float
    commentary_hint: str
    effects: WeatherEffects

    def describe(self) -> str:
        base = f"{self.label} ({self.temperature_f}°F, {self.wind_speed_mph:.1f} mph {self.wind_direction})"
        if self.precipitation != "none":
            base += f" - {self.precipitation.title()}"
        return base


_WEATHER_ARCHETYPES: List[Dict[str, object]] = [
    {
        "label": "Crisp & Calm",
        "condition": "clear",
        "precipitation": "none",
        "temp_range": (58, 70),
        "wind_range": (0.0, 5.0),
        "carry_modifier": 0.05,
        "error_modifier": -0.02,
        "wild_pitch_modifier": -0.03,
        "weight": 0.24,
        "commentary": "Perfect baseball weather with just a light breeze.",
    },
    {
        "label": "Humid Haze",
        "condition": "muggy",
        "precipitation": "none",
        "temp_range": (72, 82),
        "wind_range": (2.0, 8.0),
        "carry_modifier": 0.02,
        "error_modifier": 0.0,
        "wild_pitch_modifier": 0.01,
        "weight": 0.2,
        "commentary": "Heavy air could make the ball feel a little heavier off the bat.",
        "stamina_scalar": 1.05,
    },
    {
        "label": "Gusty Crosswinds",
        "condition": "windy",
        "precipitation": "none",
        "temp_range": (60, 75),
        "wind_range": (10.0, 18.0),
        "carry_modifier": -0.03,
        "error_modifier": 0.03,
        "wild_pitch_modifier": 0.04,
        "weight": 0.18,
        "commentary": "Crosswinds could wreak havoc on lofted balls and command alike.",
    },
    {
        "label": "Light Drizzle",
        "condition": "rain",
        "precipitation": "drizzle",
        "temp_range": (55, 68),
        "wind_range": (4.0, 12.0),
        "carry_modifier": -0.04,
        "error_modifier": 0.06,
        "wild_pitch_modifier": 0.07,
        "weight": 0.17,
        "commentary": "Slick conditions may test everyone's grip.",
        "ball_slip": 0.05,
        "grounder_speed_bonus": 2.0,
        "stamina_scalar": 1.08,
    },
    {
        "label": "Steady Rain",
        "condition": "rain",
        "precipitation": "steady",
        "temp_range": (52, 65),
        "wind_range": (6.0, 15.0),
        "carry_modifier": -0.08,
        "error_modifier": 0.12,
        "wild_pitch_modifier": 0.12,
        "weight": 0.12,
        "commentary": "Field crews are watching puddles; expect defensive miscues.",
        "ball_slip": 0.1,
        "grounder_speed_bonus": 4.0,
        "stamina_scalar": 1.12,
    },
    {
        "label": "Hot & Thin Air",
        "condition": "heat",
        "precipitation": "none",
        "temp_range": (85, 96),
        "wind_range": (3.0, 10.0),
        "carry_modifier": 0.09,
        "error_modifier": 0.02,
        "wild_pitch_modifier": 0.03,
        "weight": 0.09,
        "commentary": "Ball should really fly today but stamina will be a concern.",
        "stamina_scalar": 1.15,
    },
]


def _weighted_choice(options: Sequence[Dict[str, object]], rng) -> Dict[str, object]:
    total = sum(float(opt.get("weight", 1.0) or 1.0) for opt in options)
    pick = rng.random() * total
    upto = 0.0
    for opt in options:
        weight = float(opt.get("weight", 1.0) or 1.0)
        upto += weight
        if upto >= pick:
            return opt
    return options[-1]


def _wind_distance_delta(speed_mph: float, direction: str) -> float:
    if speed_mph <= 1.5:
        return 0.0
    magnitude = min(10.0, speed_mph * 0.6)
    direction = (direction or "").upper()
    if direction in {"S", "SE", "SW"}:
        return magnitude
    if direction in {"N", "NE", "NW"}:
        return -magnitude
    if direction == "E":
        return magnitude * 0.35
    if direction == "W":
        return -magnitude * 0.35
    return 0.0


def generate_weather_profile(rng=None) -> WeatherProfile:
    """Roll and return a weather profile complete with gameplay effects."""
    rng = rng or get_rng()
    preset = _weighted_choice(_WEATHER_ARCHETYPES, rng)
    temp_low, temp_high = preset.get("temp_range", (60, 75))
    wind_low, wind_high = preset.get("wind_range", (0.0, 5.0))
    temperature = rng.randint(int(temp_low), int(temp_high))
    wind_speed = rng.uniform(float(wind_low), float(wind_high))
    wind_direction = rng.choice(WIND_DIRECTIONS)

    effects = WeatherEffects(
        ball_slip_chance=float(preset.get("ball_slip", 0.0) or 0.0),
        stamina_drain_scalar=float(preset.get("stamina_scalar", 1.0) or 1.0),
        ground_ball_speed_bonus=float(preset.get("grounder_speed_bonus", 0.0) or 0.0),
    )

    # Heat amplifies stamina drain even without special presets.
    if temperature >= 90:
        effects = replace(effects, stamina_drain_scalar=max(effects.stamina_drain_scalar, 1.18))
    elif temperature >= 82:
        effects = replace(effects, stamina_drain_scalar=max(effects.stamina_drain_scalar, 1.08))

    fly_delta = _wind_distance_delta(wind_speed, wind_direction)
    effects = replace(effects, fly_ball_distance_delta_m=fly_delta)

    return WeatherProfile(
        label=str(preset["label"]),
        condition=str(preset["condition"]),
        precipitation=str(preset["precipitation"]),
        temperature_f=int(temperature),
        wind_speed_mph=float(round(wind_speed, 1)),
        wind_direction=str(wind_direction),
        carry_modifier=float(preset.get("carry_modifier", 0.0) or 0.0),
        error_modifier=float(preset.get("error_modifier", 0.0) or 0.0),
        wild_pitch_modifier=float(preset.get("wild_pitch_modifier", 0.0) or 0.0),
        commentary_hint=str(preset.get("commentary", "")),
        effects=effects,
    )


__all__ = ["WeatherEffects", "WeatherProfile", "WIND_DIRECTIONS", "generate_weather_profile"]
