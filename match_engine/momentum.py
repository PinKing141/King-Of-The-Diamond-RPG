"""Momentum, presence, and pressure helpers for the match engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

FLOW_THRESHOLD = 5
FLOW_BOOST_PERCENT = 0.10

MOMENTUM_EVENT_WEIGHTS: Dict[str, int] = {
    "strikeout": 1,
    "double_play": 3,
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
    """Per-team tracker that enables flow-state boosts."""

    def __init__(self, *team_ids: Optional[int]):
        self.values: Dict[Optional[int], int] = {}
        for team_id in team_ids:
            if team_id is not None:
                self.values[team_id] = 0

    def _ensure_team(self, team_id: Optional[int]) -> None:
        if team_id is None:
            return
        self.values.setdefault(team_id, 0)

    def record_event(self, team_id: Optional[int], event_key: str, delta: Optional[int] = None) -> int:
        self._ensure_team(team_id)
        if team_id is None:
            return 0
        change = delta if delta is not None else MOMENTUM_EVENT_WEIGHTS.get(event_key, 0)
        if change == 0:
            return self.values.get(team_id, 0)
        value = self.values.get(team_id, 0) + change
        self.values[team_id] = max(-10, min(15, value))
        return self.values[team_id]

    def in_flow(self, team_id: Optional[int]) -> bool:
        if team_id is None:
            return False
        return self.values.get(team_id, 0) >= FLOW_THRESHOLD

    def get_multiplier(self, team_id: Optional[int]) -> float:
        return 1.0 + (FLOW_BOOST_PERCENT if self.in_flow(team_id) else 0.0)

    def serialize(self) -> Dict[int, int]:
        return {k: v for k, v in self.values.items() if k is not None}


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
    "FLOW_THRESHOLD",
    "FLOW_BOOST_PERCENT",
    "MOMENTUM_EVENT_WEIGHTS",
    "MomentumSystem",
    "PresenceProfile",
    "PresenceSystem",
]
