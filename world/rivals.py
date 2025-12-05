"""Dynamic rivalry tracking used to add narrative stakes to marquee matchups.

The module is intentionally lightweight so world sims, match engine, UI, and
telemetry can all read/update the same rivalry state without tightly coupling to
any specific system or database schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


def _normalize_pitch(pitch_name: Optional[str]) -> Optional[str]:
    if not pitch_name:
        return None
    return pitch_name.strip().lower()


@dataclass
class Rival:
    """Head-to-head ledger between the hero (user) and a rival player."""

    hero_id: int
    rival_id: int
    win_loss_record: Dict[str, int] = field(default_factory=lambda: {"wins": 0, "losses": 0})
    strikeouts_against: Dict[str, int] = field(default_factory=dict)
    heat_level: float = 35.0
    _active_adaptation_pitch: Optional[str] = None
    _pending_adaptation_pitch: Optional[str] = None

    def activate_match(self) -> Optional[str]:
        """Carry any staged adaptation into the live match context."""
        self._active_adaptation_pitch = self._pending_adaptation_pitch
        self._pending_adaptation_pitch = None
        return self._active_adaptation_pitch

    def record_game_result(self, hero_won: bool) -> None:
        key = "wins" if hero_won else "losses"
        self.win_loss_record[key] = self.win_loss_record.get(key, 0) + 1
        swing = 4.0 if hero_won else -2.5
        self.heat_level = max(0.0, min(100.0, self.heat_level + swing))

    def record_strikeout(self, pitch_name: Optional[str]) -> None:
        slug = _normalize_pitch(pitch_name)
        if not slug:
            return
        self.strikeouts_against[slug] = self.strikeouts_against.get(slug, 0) + 1
        # Stage an adaptation for the next time these players meet.
        self._pending_adaptation_pitch = slug
        self.heat_level = max(20.0, min(100.0, self.heat_level + 3.0))

    def recognition_bonus(self, pitch_name: Optional[str]) -> float:
        slug = _normalize_pitch(pitch_name)
        if slug and slug == self._active_adaptation_pitch:
            return 0.2
        return 0.0

    def describe(self) -> Dict[str, object]:
        return {
            "hero_id": self.hero_id,
            "rival_id": self.rival_id,
            "record": dict(self.win_loss_record),
            "strikeouts_against": dict(self.strikeouts_against),
            "heat_level": round(self.heat_level, 2),
            "active_adaptation": self._active_adaptation_pitch,
        }


@dataclass
class RivalMatchContext:
    """Runtime helper bound to a specific matchup instance."""

    rival: Rival
    hero_team_id: Optional[int] = None
    rival_team_id: Optional[int] = None

    def begin_match(self) -> None:
        self.rival.activate_match()

    def is_rival_plate(self, batter_id: Optional[int]) -> bool:
        return bool(batter_id and batter_id == self.rival.rival_id)

    def is_hero_pitching(self, pitcher_id: Optional[int]) -> bool:
        return bool(pitcher_id and pitcher_id == self.rival.hero_id)

    def recognition_bonus(self, batter_id: Optional[int], pitch_name: Optional[str]) -> float:
        if not self.is_rival_plate(batter_id):
            return 0.0
        return self.rival.recognition_bonus(pitch_name)

    def note_strikeout(self, batter_id: Optional[int], pitcher_id: Optional[int], pitch_name: Optional[str]) -> None:
        if not (self.is_rival_plate(batter_id) and self.is_hero_pitching(pitcher_id)):
            return
        self.rival.record_strikeout(pitch_name)

    def finalize(self, winner_team_id: Optional[int]) -> None:
        if winner_team_id is None:
            return
        if self.hero_team_id and winner_team_id == self.hero_team_id:
            self.rival.record_game_result(hero_won=True)
        elif self.hero_team_id:
            self.rival.record_game_result(hero_won=False)


class RivalryLedger:
    """Process-wide registry that keeps rivalry stats in memory."""

    def __init__(self) -> None:
        self._pairs: Dict[Tuple[int, int], Rival] = {}

    def get(self, hero_id: int, rival_id: int) -> Rival:
        key = (hero_id, rival_id)
        if key not in self._pairs:
            self._pairs[key] = Rival(hero_id=hero_id, rival_id=rival_id)
        return self._pairs[key]

    def create_match_context(
        self,
        hero_id: int,
        rival_id: int,
        *,
        hero_team_id: Optional[int] = None,
        rival_team_id: Optional[int] = None,
    ) -> RivalMatchContext:
        rival = self.get(hero_id, rival_id)
        ctx = RivalMatchContext(rival=rival, hero_team_id=hero_team_id, rival_team_id=rival_team_id)
        ctx.begin_match()
        return ctx


_LEDGER = RivalryLedger()


def get_ledger() -> RivalryLedger:
    return _LEDGER
