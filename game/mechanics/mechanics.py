from __future__ import annotations

import hashlib
import json
import random
import logging
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence, Tuple

from sqlalchemy.exc import SQLAlchemyError

from core.paths import data_path
from core.rng import get_rng

logger = logging.getLogger(__name__)


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


def _load_list(path, default: Sequence[str]) -> Sequence[str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return tuple(str(item) for item in data)
    except FileNotFoundError:
        return tuple(default)
    return tuple(default)


DATA_ROOT = data_path()

_ARM_SLOTS: Sequence[str] = _load_list(
    data_path("arm_slots.json"),
    (
        "Over-the-Top",
        "Three-Quarters",
        "Sidearm",
        "Low Three-Quarters",
    ),
)
_POSTURES = ("closed", "neutral", "open")
_SIGNATURE_ADJECTIVES = _load_list(
    data_path("signature_adjectives.json"),
    ("Lab", "Whip", "Tower", "Glide", "Orbit", "Storm", "Echo", "Pulse", "Spiral", "Latch"),
)
_NOTES = (
    "Late hip fire",
    "Hides ball forever",
    "Explosive finish",
    "Deceptive pause",
    "Marathon stride",
    "Razor release",
)

# --- Mechanics tuning knobs (document intent) ---
AVG_AGGRESSION = 50
AGGRESSION_TEMPO_DIVISOR = 200.0
AVG_STAMINA = 60
STAMINA_TEMPO_DIVISOR = 180.0
BASE_TEMPO_SECONDS = 0.45
TEMPO_NOISE_RANGE = (-0.1, 0.15)
MIN_TEMPO_SECONDS = 0.2
MAX_TEMPO_SECONDS = 1.2

BASE_EXTENSION_FEET = 5.2
BASELINE_HEIGHT_INCHES = 72
EXTENSION_PER_INCH_OF_HEIGHT = 0.03
EXTENSION_PER_WINGSPAN_INCH = 0.015
EXTENSION_NOISE_RANGE = (-0.25, 0.35)
MIN_EXTENSION_FEET = 4.6
MAX_EXTENSION_FEET = 7.8

RELEASE_HEIGHT_MIN = 4.2
RELEASE_HEIGHT_MAX = 6.8
ARM_SLOT_DROP = {"Over-the-Top": 0.0, "Three-Quarters": 0.5, "Low Three-Quarters": 0.9, "Sidearm": 1.4}
DEFAULT_ARM_SLOT_DROP = 0.5

AVG_EXTENSION_FEET = 6.0
PERCEIVED_VELO_PER_FOOT = 0.65
TEMPO_VELO_SCALAR = 4.5
MIN_PERCEIVED_VELO = -2.0
MAX_PERCEIVED_VELO = 4.5

BALANCE_COMMAND_SCALAR = 0.25
HIGH_TEMPO_THRESHOLD = 0.85
HIGH_TEMPO_COMMAND_PENALTY = 0.05
MIN_COMMAND_SCALAR = 0.75
MAX_COMMAND_SCALAR = 1.25

DECEPTION_MOVEMENT_SCALAR = 0.2
RIDE_CLAMP = (0.8, 1.25)
SINK_CLAMP = (0.8, 1.2)
SWEEP_CLAMP = (0.8, 1.3)
ARM_SLOT_VERTICAL_BONUS = {"Over-the-Top": 0.12, "Sidearm": -0.08}
ARM_SLOT_HORIZONTAL_BONUS = {"Over-the-Top": -0.05, "Sidearm": 0.2, "Low Three-Quarters": 0.1}
POSTURE_HORIZONTAL_BONUS = 0.05
POSTURE_VERTICAL_BONUS = 0.05


def _seed_from_pitcher(pitcher, seed: Optional[int]) -> int:
    if seed is not None:
        return seed
    pitcher_id = getattr(pitcher, "id", None) or 0
    jersey = getattr(pitcher, "jersey_number", 0) or 0
    name = getattr(pitcher, "last_name", getattr(pitcher, "name", "")) or ""
    name_hash = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return (pitcher_id * 7919) ^ (jersey * 271) ^ name_hash


def _random_for_pitcher(pitcher, seed: Optional[int]) -> random.Random:
    prng = random.Random()
    base = _seed_from_pitcher(pitcher, seed)
    prng.seed(base & 0xFFFFFFFF)
    return prng


def _tempo_for_pitcher(pitcher, prng: random.Random) -> float:
    stamina = getattr(pitcher, "stamina", 55) or 55
    aggression = getattr(pitcher, "aggression", 55) or 55
    base = BASE_TEMPO_SECONDS + (aggression - AVG_AGGRESSION) / AGGRESSION_TEMPO_DIVISOR
    base += (stamina - AVG_STAMINA) / STAMINA_TEMPO_DIVISOR
    noise = prng.uniform(*TEMPO_NOISE_RANGE)
    return max(MIN_TEMPO_SECONDS, min(MAX_TEMPO_SECONDS, base + noise))


def _extension_for_pitcher(pitcher, prng: random.Random) -> float:
    height = getattr(pitcher, "height_inches", 74) or 74
    wingspan_bonus = getattr(pitcher, "wingspan", height) - height
    base = BASE_EXTENSION_FEET + (height - BASELINE_HEIGHT_INCHES) * EXTENSION_PER_INCH_OF_HEIGHT
    base += wingspan_bonus * EXTENSION_PER_WINGSPAN_INCH
    noise = prng.uniform(*EXTENSION_NOISE_RANGE)
    return max(MIN_EXTENSION_FEET, min(MAX_EXTENSION_FEET, base + noise))


def _release_height(pitcher, prng: random.Random) -> float:
    height = getattr(pitcher, "height_inches", 74) or 74
    slot = getattr(pitcher, "arm_slot", None) or prng.choice(_ARM_SLOTS)
    drop = ARM_SLOT_DROP.get(slot, DEFAULT_ARM_SLOT_DROP)
    return max(RELEASE_HEIGHT_MIN, min(RELEASE_HEIGHT_MAX, (height / 12) - drop + prng.uniform(-0.15, 0.15)))


def _perceived_velocity_bonus(extension: float, tempo: float) -> float:
    ext_bonus = (extension - AVG_EXTENSION_FEET) * PERCEIVED_VELO_PER_FOOT
    tempo_bonus = (tempo - 0.5) * TEMPO_VELO_SCALAR
    return round(max(MIN_PERCEIVED_VELO, min(MAX_PERCEIVED_VELO, ext_bonus + tempo_bonus)), 2)


def _command_scalar(balance: float, tempo: float) -> float:
    base = 1.0 + (balance - 0.5) * BALANCE_COMMAND_SCALAR
    if tempo > HIGH_TEMPO_THRESHOLD:
        base -= HIGH_TEMPO_COMMAND_PENALTY
    return max(MIN_COMMAND_SCALAR, min(MAX_COMMAND_SCALAR, base))


def _movement_bias(arm_slot: str, posture: str, deception: float) -> Dict[str, float]:
    vertical = 1.0
    horizontal = 1.0
    if arm_slot == "Over-the-Top":
        vertical += ARM_SLOT_VERTICAL_BONUS["Over-the-Top"]
        horizontal += ARM_SLOT_HORIZONTAL_BONUS["Over-the-Top"]
    elif arm_slot == "Sidearm":
        horizontal += ARM_SLOT_HORIZONTAL_BONUS["Sidearm"]
        vertical += ARM_SLOT_VERTICAL_BONUS["Sidearm"]
    elif arm_slot == "Low Three-Quarters":
        horizontal += ARM_SLOT_HORIZONTAL_BONUS["Low Three-Quarters"]
    if posture == "closed":
        horizontal += POSTURE_HORIZONTAL_BONUS
    elif posture == "open":
        vertical += POSTURE_VERTICAL_BONUS
    deception_bonus = (deception - 0.5) * DECEPTION_MOVEMENT_SCALAR
    return {
        "ride": max(RIDE_CLAMP[0], min(RIDE_CLAMP[1], vertical + deception_bonus)),
        "sink": max(SINK_CLAMP[0], min(SINK_CLAMP[1], vertical - deception_bonus * 0.5)),
        "sweep": max(SWEEP_CLAMP[0], min(SWEEP_CLAMP[1], horizontal + deception_bonus * 0.75)),
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


def _serialize_profile(profile: PitchingMechanicsProfile) -> Dict[str, object]:
    return {
        "pitcher_id": profile.pitcher_id,
        "signature": profile.signature,
        "arm_slot": profile.arm_slot,
        "posture": profile.posture,
        "tempo": profile.tempo,
        "deception": profile.deception,
        "balance": profile.balance,
        "aggression": profile.aggression,
        "release_height": profile.release_height,
        "extension": profile.extension,
        "perceived_velocity_bonus": profile.perceived_velocity_bonus,
        "command_scalar": profile.command_scalar,
        "movement_bias": profile.movement_bias,
        "notes": list(profile.notes),
    }


def _hydrate_profile(payload: dict, pitcher_id: Optional[int]) -> Optional[PitchingMechanicsProfile]:
    try:
        return PitchingMechanicsProfile(
            pitcher_id=pitcher_id or payload.get("pitcher_id"),
            signature=payload["signature"],
            arm_slot=payload["arm_slot"],
            posture=payload.get("posture", "neutral"),
            tempo=float(payload.get("tempo", 0.5)),
            deception=float(payload.get("deception", 0.6)),
            balance=float(payload.get("balance", 0.55)),
            aggression=float(payload.get("aggression", 0.5)),
            release_height=float(payload.get("release_height", 5.5)),
            extension=float(payload.get("extension", 6.0)),
            perceived_velocity_bonus=float(payload.get("perceived_velocity_bonus", 0.0)),
            command_scalar=float(payload.get("command_scalar", 1.0)),
            movement_bias={
                "ride": float(payload.get("movement_bias", {}).get("ride", 1.0)),
                "sink": float(payload.get("movement_bias", {}).get("sink", 1.0)),
                "sweep": float(payload.get("movement_bias", {}).get("sweep", 1.0)),
            },
            notes=tuple(payload.get("notes", ())),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _load_profile_from_json(raw: Optional[str], pitcher_id: Optional[int]) -> Optional[PitchingMechanicsProfile]:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return _hydrate_profile(payload, pitcher_id)


def _persist_profile(state, pitcher, profile: PitchingMechanicsProfile, *, pitcher_id: Optional[int]) -> None:
    if pitcher_id is None:
        return
    mechanics_json = json.dumps(_serialize_profile(profile))
    if hasattr(pitcher, "mechanics_json"):
        try:
            pitcher.mechanics_json = mechanics_json
        except (AttributeError, TypeError, ValueError):
            return
    session = getattr(state, "db_session", None)
    if session is None:
        return
    try:
        session.add(pitcher)
        session.flush()
    except SQLAlchemyError as exc:
        logger.debug("Persisting mechanics profile failed for %s: %s", pitcher_id, exc)
        try:
            session.rollback()
        except SQLAlchemyError:
            pass


def get_or_create_profile(state, pitcher) -> PitchingMechanicsProfile:
    cache = getattr(state, "pitcher_mechanics", None)
    if cache is None:
        cache = {}
        state.pitcher_mechanics = cache
    pitcher_id = getattr(pitcher, "id", None)
    if pitcher_id in cache:
        return cache[pitcher_id]
    stored = _load_profile_from_json(getattr(pitcher, "mechanics_json", None), pitcher_id)
    profile = stored or generate_mechanics_profile(pitcher)
    if pitcher_id is not None:
        cache[pitcher_id] = profile
        if stored is None:
            _persist_profile(state, pitcher, profile, pitcher_id=pitcher_id)
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
