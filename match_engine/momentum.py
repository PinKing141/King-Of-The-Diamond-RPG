"""Momentum, presence, and pressure helpers for the match engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from core.event_bus import EventBus

from .states import EventType

METER_MIN = -20
METER_MAX = 20
ZONE_THRESHOLD = 10
ZONE_BONUS = 0.05
BASE_POINT_SCALAR = 0.01
STRIKEOUT_POINTS = 2
DOUBLE_PLAY_POINTS = 4
HIT_POINT_TABLE = {"1B": 1, "2B": 2, "3B": 3, "HR": 5}

MOMENTUM_EVENT_WEIGHTS: Dict[str, int] = {
    "strikeout": STRIKEOUT_POINTS,
    "double_play": DOUBLE_PLAY_POINTS,
    "error": -2,
}

ACE_POSITIVE_TRIGGERS: Dict[str, float] = {
    "strikeout_full_count": 8.0,
    "escape_bases_loaded": 12.0,
    "strikeout_cleanup": 9.0,
}
ACE_NEGATIVE_TRIGGERS: Dict[str, float] = {
    "walk_batter": -5.0,
    "hit_allowed_to_pitcher": -6.0,
    "visible_frustration": -8.0,
}

CLEANUP_POSITIVE_TRIGGERS: Dict[str, float] = {
    "extra_base_hit": 9.0,
    "rbi": 7.0,
    "walk_from_02": 6.0,
}
CLEANUP_NEGATIVE_TRIGGERS: Dict[str, float] = {
    "strikeout_swinging": -7.0,
    "double_play": -10.0,
}


@dataclass
class PresenceProfile:
    """Tracks the presence meter for a pillar player."""

    player_id: int
    team_id: Optional[int]
    role: str  # "ACE" or "CLEANUP"
    trust_baseline: int = 50
    value: float = 50.0
    zone_threshold: float = 80.0
    in_zone: bool = False

    def trust_state(self) -> str:
        baseline = self.trust_baseline or 50
        if baseline >= 65:
            return "HIGH"
        if baseline <= 40:
            return "LOW"
        return "NEUTRAL"

    def apply_delta(self, delta: float) -> float:
        self.value = max(0.0, min(100.0, self.value + delta))
        self.in_zone = self.value >= self.zone_threshold
        return self.value


class MomentumSystem:
    """Tug-of-war momentum meter that reacts to EventBus traffic."""

    def __init__(
        self,
        home_team_id: Optional[int],
        away_team_id: Optional[int],
        *,
        bus: Optional[EventBus] = None,
    ) -> None:
        self.home_team_id = home_team_id
        self.away_team_id = away_team_id
        self.meter: float = 0.0
        self.bus: Optional[EventBus] = None
        self._zone_owner: Optional[str] = None  # "home" | "away"
        self._subscriptions: List[Tuple[str, Callable[[Dict[str, Any]], None]]] = []
        if bus:
            self.attach_bus(bus)

    # -- Event wiring -------------------------------------------------
    def attach_bus(self, bus: Optional[EventBus]) -> None:
        if bus is self.bus:
            return
        self.detach_bus()
        if bus is None:
            self.bus = None
            return
        self.bus = bus
        handlers = [
            (EventType.STRIKEOUT.value, self._handle_strikeout),
            (EventType.PLAY_RESULT.value, self._handle_play_result),
        ]
        for event_name, handler in handlers:
            bus.subscribe(event_name, handler)
        self._subscriptions = handlers

    def detach_bus(self) -> None:
        if not self.bus:
            self._subscriptions = []
            return
        for event_name, handler in self._subscriptions:
            self.bus.unsubscribe(event_name, handler)
        self._subscriptions = []
        self.bus = None

    # -- Public API used by the rest of the engine -------------------
    def record_event(self, team_id: Optional[int], event_key: str, delta: Optional[int] = None) -> int:
        side = self._side_for_team(team_id)
        if side is None:
            return int(self.meter)
        change = delta if delta is not None else MOMENTUM_EVENT_WEIGHTS.get(event_key, 0)
        if change == 0:
            return int(self.meter)
        self._apply_delta(side, change)
        return int(self.meter)

    def get_multiplier(self, team_id: Optional[int]) -> float:
        side = self._side_for_team(team_id)
        if side is None:
            return 1.0
        return self.get_momentum_modifier(side)

    def get_momentum_modifier(self, team_side: Optional[str]) -> float:
        if team_side not in {"home", "away"}:
            return 1.0
        value = self.meter if team_side == "home" else -self.meter
        if value <= 0:
            return 1.0
        modifier = 1.0 + (value * BASE_POINT_SCALAR)
        if self._zone_owner == team_side:
            modifier += ZONE_BONUS
        return round(modifier, 3)

    def serialize(self) -> Dict[str, float]:
        return {
            "meter": self.meter,
            "zone": self._zone_owner or "neutral",
        }

    # -- Event handlers -----------------------------------------------
    def _handle_strikeout(self, payload: Dict[str, Any]) -> None:
        half = payload.get("half")
        side = payload.get("fielding_team") or self._fielding_side_from_half(half)
        if side:
            self._apply_delta(side, STRIKEOUT_POINTS)

    def _handle_play_result(self, payload: Dict[str, Any]) -> None:
        batting = payload.get("batting_team") or self._batting_side_from_half(payload.get("half"))
        fielding = payload.get("fielding_team") or self._fielding_side_from_half(payload.get("half"))
        hit_type = (payload.get("hit_type") or "").upper()
        double_play = bool(payload.get("double_play"))
        error_flag = bool(payload.get("error_on_play"))

        if double_play and fielding:
            self._apply_delta(fielding, DOUBLE_PLAY_POINTS)
        if hit_type in HIT_POINT_TABLE and batting:
            self._apply_delta(batting, HIT_POINT_TABLE[hit_type])
        if error_flag and fielding:
            self._apply_delta(fielding, MOMENTUM_EVENT_WEIGHTS.get("error", -2))

    # -- Internal helpers ---------------------------------------------
    def _apply_delta(self, team_side: str, amount: int | float) -> None:
        if not amount or team_side not in {"home", "away"}:
            return
        direction = 1 if team_side == "home" else -1
        previous_meter = self.meter
        self.meter = max(METER_MIN, min(METER_MAX, self.meter + (direction * amount)))
        self._evaluate_zone(previous_meter)

    def _evaluate_zone(self, previous_meter: float) -> None:
        zone: Optional[str]
        if self.meter > ZONE_THRESHOLD:
            zone = "home"
        elif self.meter < -ZONE_THRESHOLD:
            zone = "away"
        else:
            zone = None
        if zone == self._zone_owner:
            return
        self._zone_owner = zone
        if not self.bus:
            return
        payload = {
            "team_side": zone,
            "meter": self.meter,
            "modifier": self.get_momentum_modifier(zone) if zone else 1.0,
        }
        self.bus.publish(EventType.MOMENTUM_SHIFT.value, payload)

    def _side_for_team(self, team_id: Optional[int]) -> Optional[str]:
        if team_id and team_id == self.home_team_id:
            return "home"
        if team_id and team_id == self.away_team_id:
            return "away"
        return None

    @staticmethod
    def _batting_side_from_half(half: Optional[str]) -> str:
        if (half or "Top").lower().startswith("t"):
            return "away"
        return "home"

    @staticmethod
    def _fielding_side_from_half(half: Optional[str]) -> str:
        if (half or "Top").lower().startswith("t"):
            return "home"
        return "away"


class PresenceSystem:
    """Manages pillar presence levels and derived aura effects."""

    def __init__(self, profiles: Optional[Iterable[PresenceProfile]] = None):
        self._profiles: Dict[int, PresenceProfile] = {}
        if profiles:
            self.configure(profiles)

    def configure(self, profiles: Iterable[PresenceProfile]) -> None:
        self._profiles = {profile.player_id: profile for profile in profiles if profile.player_id}

    def get_profile(self, player_id: Optional[int]) -> Optional[PresenceProfile]:
        if not player_id:
            return None
        return self._profiles.get(player_id)

    def register_trigger(self, player_id: Optional[int], trigger_key: str) -> Optional[PresenceProfile]:
        profile = self.get_profile(player_id)
        if not profile:
            return None
        delta = self._lookup_delta(profile.role, trigger_key)
        if delta == 0:
            return profile
        profile.apply_delta(delta)
        return profile

    def decay_towards_neutral(self, amount: float = 1.5) -> None:
        for profile in self._profiles.values():
            if profile.value > 50.0:
                profile.apply_delta(-amount)
            elif profile.value < 50.0:
                profile.apply_delta(amount)

    def _lookup_delta(self, role: str, trigger_key: str) -> float:
        if role == "ACE":
            if trigger_key in ACE_POSITIVE_TRIGGERS:
                return ACE_POSITIVE_TRIGGERS[trigger_key]
            if trigger_key in ACE_NEGATIVE_TRIGGERS:
                return ACE_NEGATIVE_TRIGGERS[trigger_key]
        elif role == "CLEANUP":
            if trigger_key in CLEANUP_POSITIVE_TRIGGERS:
                return CLEANUP_POSITIVE_TRIGGERS[trigger_key]
            if trigger_key in CLEANUP_NEGATIVE_TRIGGERS:
                return CLEANUP_NEGATIVE_TRIGGERS[trigger_key]
        return 0.0

    def active_auras(self) -> List[PresenceProfile]:
        return [profile for profile in self._profiles.values() if profile.in_zone]

    def aura_context(self, team_id: Optional[int]) -> Dict[str, Dict[str, str]]:
        data: Dict[str, Dict[str, str]] = {}
        for profile in self._profiles.values():
            if profile.team_id != team_id or not profile.in_zone:
                continue
            trust_state = profile.trust_state()
            if profile.role == "ACE":
                mode = "guardian" if trust_state == "HIGH" else "prima_donna" if trust_state == "LOW" else "neutral"
                data["ace"] = {
                    "player_id": str(profile.player_id),
                    "mode": mode,
                }
            elif profile.role == "CLEANUP":
                mode = "savior" if trust_state == "HIGH" else "glory_hog" if trust_state == "LOW" else "neutral"
                data["cleanup"] = {
                    "player_id": str(profile.player_id),
                    "mode": mode,
                }
        return data


__all__ = [
    "MOMENTUM_EVENT_WEIGHTS",
    "MomentumSystem",
    "PresenceProfile",
    "PresenceSystem",
]
