from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence, Tuple

from game.rng import get_rng


@dataclass(frozen=True)
class MechanicsAdjustment:
    """Lightweight container describing how mechanics tilt a single pitch."""

    velocity_bonus: float = 0.0
    control_bonus: float = 0.0
    movement_scalar: float = 1.0
    deception_bonus: float = 0.0
    perception_penalty: float = 0.0
    tags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PitchingMechanicsProfile:
    """Procedurally generated signature describing a pitcher's delivery."""

    pitcher_id: Optional[int]
    signature: str
    arm_slot: str
    posture: str
    tempo: float
    deception: float
    balance: float
    aggression: float
    release_height: float
    extension: float
    perceived_velocity_bonus: float
    command_scalar: float
    movement_bias: Dict[str, float]
    notes: Tuple[str, ...]

    def describe(self) -> Dict[str, object]:
        return {
            "pitcher_id": self.pitcher_id,
            "signature": self.signature,
            "arm_slot": self.arm_slot,
            "posture": self.posture,
            "tempo": round(self.tempo, 2),
            "deception": round(self.deception, 2),
            "balance": round(self.balance, 2),
            "aggression": round(self.aggression, 2),
            "release_height": round(self.release_height, 2),
            "extension": round(self.extension, 2),
            "perceived_velocity_bonus": round(self.perceived_velocity_bonus, 2),
            "command_scalar": round(self.command_scalar, 3),
            "movement_bias": {k: round(v, 3) for k, v in self.movement_bias.items()},
            "notes": self.notes,
        }


_ARM_SLOTS: Sequence[str] = (
    "Over-the-Top",
    "Three-Quarters",
    "Sidearm",
    "Low Three-Quarters",
)
_POSTURES = ("closed", "neutral", "open")
_SIGNATURE_ADJECTIVES = (
    "Lab", "Whip", "Tower", "Glide", "Orbit", "Storm", "Echo", "Pulse", "Spiral", "Latch"
)
_NOTES = (
    "Late hip fire",
    "Hides ball forever",
    "Explosive finish",
    "Deceptive pause",
    "Marathon stride",
    "Razor release",
)


def _seed_from_pitcher(pitcher, seed: Optional[int]) -> int:
    if seed is not None:
        return seed
    pitcher_id = getattr(pitcher, "id", None) or 0
    jersey = getattr(pitcher, "jersey_number", 0) or 0
    name = getattr(pitcher, "last_name", getattr(pitcher, "name", "")) or ""
    return (pitcher_id * 7919) ^ (jersey * 271) ^ hash(name)


def _random_for_pitcher(pitcher, seed: Optional[int]) -> random.Random:
    prng = random.Random()
    base = _seed_from_pitcher(pitcher, seed)
    prng.seed(base & 0xFFFFFFFF)
    return prng


def _tempo_for_pitcher(pitcher, prng: random.Random) -> float:
    stamina = getattr(pitcher, "stamina", 55) or 55
    aggression = getattr(pitcher, "aggression", 55) or 55
    base = 0.45 + (aggression - 50) / 200.0
    base += (stamina - 60) / 180.0
    return max(0.2, min(1.2, base + prng.uniform(-0.1, 0.15)))


def _extension_for_pitcher(pitcher, prng: random.Random) -> float:
    height = getattr(pitcher, "height_inches", 74) or 74
    wingspan_bonus = getattr(pitcher, "wingspan", height) - height
    base = 5.2 + (height - 72) * 0.03 + wingspan_bonus * 0.015
    return max(4.6, min(7.8, base + prng.uniform(-0.25, 0.35)))


def _release_height(pitcher, prng: random.Random) -> float:
    height = getattr(pitcher, "height_inches", 74) or 74
    slot = getattr(pitcher, "arm_slot", None) or prng.choice(_ARM_SLOTS)
    drop = {"Over-the-Top": 0.0, "Three-Quarters": 0.5, "Low Three-Quarters": 0.9, "Sidearm": 1.4}
    return max(4.2, min(6.8, (height / 12) - drop.get(slot, 0.5) + prng.uniform(-0.15, 0.15)))


def _perceived_velocity_bonus(extension: float, tempo: float) -> float:
    ext_bonus = (extension - 6.0) * 0.65
    tempo_bonus = (tempo - 0.5) * 4.5
    return round(max(-2.0, min(4.5, ext_bonus + tempo_bonus)), 2)


def _command_scalar(balance: float, tempo: float) -> float:
    base = 1.0 + (balance - 0.5) * 0.25
    if tempo > 0.85:
        base -= 0.05
    return max(0.75, min(1.25, base))


def _movement_bias(arm_slot: str, posture: str, deception: float) -> Dict[str, float]:
    vertical = 1.0
    horizontal = 1.0
    if arm_slot == "Over-the-Top":
        vertical += 0.12
        horizontal -= 0.05
    elif arm_slot == "Sidearm":
        horizontal += 0.2
        vertical -= 0.08
    elif arm_slot == "Low Three-Quarters":
        horizontal += 0.1
    if posture == "closed":
        horizontal += 0.05
    elif posture == "open":
        vertical += 0.05
    deception_bonus = (deception - 0.5) * 0.2
    return {
        "ride": max(0.8, min(1.25, vertical + deception_bonus)),
        "sink": max(0.8, min(1.2, vertical - deception_bonus * 0.5)),
        "sweep": max(0.8, min(1.3, horizontal + deception_bonus * 0.75)),
    }


def _notes(prng: random.Random) -> Tuple[str, ...]:
    chosen = prng.sample(_NOTES, k=2)
    return tuple(chosen)


def generate_mechanics_profile(pitcher, *, seed: Optional[int] = None) -> PitchingMechanicsProfile:
    prng = _random_for_pitcher(pitcher, seed)
    slot = getattr(pitcher, "arm_slot", None) or prng.choice(_ARM_SLOTS)
    posture = prng.choice(_POSTURES)
    tempo = _tempo_for_pitcher(pitcher, prng)
    deception = max(0.25, min(1.25, 0.6 + prng.uniform(-0.2, 0.25)))
    balance = max(0.25, min(1.25, 0.55 + prng.uniform(-0.2, 0.2)))
    aggression = max(0.25, min(1.25, 0.5 + prng.uniform(-0.15, 0.3)))
    extension = _extension_for_pitcher(pitcher, prng)
    release_height = _release_height(pitcher, prng)
    pv_bonus = _perceived_velocity_bonus(extension, tempo)
    command_scalar = _command_scalar(balance, tempo)
    movement_bias = _movement_bias(slot, posture, deception)
    signature = f"{prng.choice(_SIGNATURE_ADJECTIVES)} {getattr(pitcher, 'last_name', 'Form')}"
    notes = _notes(prng)
    return PitchingMechanicsProfile(
        pitcher_id=getattr(pitcher, "id", None),
        signature=signature,
        arm_slot=slot,
        posture=posture,
        tempo=tempo,
        deception=deception,
        balance=balance,
        aggression=aggression,
        release_height=release_height,
        extension=extension,
        perceived_velocity_bonus=pv_bonus,
        command_scalar=command_scalar,
        movement_bias=movement_bias,
        notes=notes,
    )


def generate_unique_form(
    pitcher,
    *,
    seed: Optional[int] = None,
    profile: Optional[PitchingMechanicsProfile] = None,
) -> Dict[str, object]:
    """Derive delivery-facing modifiers used by pitch physics.

    Notes
    -----
    - "hiding_factor" scales how well the ball is hidden; values >1.0 shrink reaction time.
    - "extension" is reused directly to boost perceived velocity in-flight adjustments.
    """

    base_profile = profile or generate_mechanics_profile(pitcher, seed=seed)
    deception = base_profile.deception
    hiding = 1.0 + (deception - 0.6) * 0.55
    if base_profile.posture == "closed":
        hiding += 0.05
    elif base_profile.posture == "open":
        hiding -= 0.03
    if base_profile.arm_slot in {"Sidearm", "Low Three-Quarters"}:
        hiding += 0.02
    hiding = max(0.85, min(1.2, hiding))

    return {
        "profile": base_profile,
        "signature": base_profile.signature,
        "extension": base_profile.extension,
        "release_height": base_profile.release_height,
        "hiding_factor": hiding,
    }


def get_or_create_profile(state, pitcher) -> PitchingMechanicsProfile:
    cache = getattr(state, "pitcher_mechanics", None)
    if cache is None:
        cache = {}
        state.pitcher_mechanics = cache
    pitcher_id = getattr(pitcher, "id", None)
    if pitcher_id in cache:
        return cache[pitcher_id]
    profile = generate_mechanics_profile(pitcher)
    if pitcher_id is not None:
        cache[pitcher_id] = profile
    return profile


def mechanics_adjustment_for_pitch(
    profile: PitchingMechanicsProfile,
    pitch_definition: Dict[str, object],
    *,
    location: str = "Zone",
) -> MechanicsAdjustment:
    family = (pitch_definition.get("family") or "Generic").lower()
    plane = (pitch_definition.get("plane") or "ride").lower()
    tags: Tuple[str, ...] = ()
    movement_scalar = profile.movement_bias.get("ride", 1.0)
    if plane == "sink":
        movement_scalar = profile.movement_bias.get("sink", movement_scalar)
    elif plane in {"sweep", "horizontal"}:
        movement_scalar = profile.movement_bias.get("sweep", movement_scalar)

    velocity_bonus = profile.perceived_velocity_bonus
    if family in {"fastball", "cutter"}:
        velocity_bonus += profile.aggression * 0.8
    elif family in {"changeup", "splitter"}:
        velocity_bonus -= 1.5 * profile.tempo

    control_bonus = (profile.command_scalar - 1.0) * 12
    deception_bonus = (profile.deception - 0.5) * 8
    perception_penalty = max(0.0, profile.deception - 0.6) * 6

    if location == "Chase":
        control_bonus -= 1.5 * (profile.tempo - 0.5)
        deception_bonus += 0.8
    if profile.posture == "closed" and family in {"breaking", "slider"}:
        movement_scalar *= 1.05
        tags += ("Closed-hip sweep",)
    if profile.arm_slot == "Sidearm" and plane in {"sweep", "horizontal"}:
        movement_scalar *= 1.08
        tags += ("Sidearm sweep boost",)

    movement_scalar = max(0.85, min(1.25, movement_scalar))

    return MechanicsAdjustment(
        velocity_bonus=velocity_bonus,
        control_bonus=control_bonus,
        movement_scalar=movement_scalar,
        deception_bonus=deception_bonus,
        perception_penalty=perception_penalty,
        tags=tags or profile.notes,
    )


def describe_mechanics(state, pitchers: Iterable) -> Dict[int, Dict[str, object]]:
    summaries: Dict[int, Dict[str, object]] = {}
    for pitcher in pitchers:
        if not pitcher:
            continue
        profile = get_or_create_profile(state, pitcher)
        pitcher_id = getattr(pitcher, "id", None)
        if pitcher_id is not None:
            summaries[pitcher_id] = profile.describe()
    return summaries


__all__ = [
    "MechanicsAdjustment",
    "PitchingMechanicsProfile",
    "generate_unique_form",
    "generate_mechanics_profile",
    "get_or_create_profile",
    "mechanics_adjustment_for_pitch",
    "describe_mechanics",
]
