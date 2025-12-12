from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PlayerXPEntryDTO:
    stat_key: str
    xp: float


@dataclass
class PitchRepertoireDTO:
    pitch_name: str
    mastery_level: int
    mastery_xp: int
    h_break_mult: float = 1.0
    v_break_mult: float = 1.0
    release_height: float = 6.0
    extension: float = 6.0


@dataclass
class PlayerTrainingDTO:
    id: Optional[int]
    school_id: Optional[int]
    position: Optional[str]
    growth_tag: Optional[str]
    conditioning: float
    fatigue: int
    injury_days: int
    jersey_number: Optional[int]
    slump_timer: int
    stats: Dict[str, float] = field(default_factory=dict)
    pitch_repertoire: List[PitchRepertoireDTO] = field(default_factory=list)
    xp_entries: List[PlayerXPEntryDTO] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamDTO:
    id: Optional[int]
    name: str
    prestige: int
    era: Optional[str] = None
    era_momentum: int = 0
