from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class PlayerDTO:
    id: int
    school_id: Optional[int]
    fatigue: int
    growth_tag: Optional[str] = None
    conditioning: int = 50
    injury_days: int = 0
    jersey_number: Optional[int] = None
    position: Optional[str] = None
    slump_timer: int = 0
    stats: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class TeamDTO:
    id: int
    name: str
    prestige: int = 0
    era_label: Optional[str] = None
    era_momentum: int = 0
