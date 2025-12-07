"""Lightweight tracker for multi-week narrative arcs.

This module is intentionally decoupled from the event manager so arcs can be
checked/advanced from weekly schedulers, UI layers, or tests without pulling in
interactive dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class StoryArc:
    key: str
    week: int = 1
    score: float = 0.0
    metadata: Dict[str, object] = field(default_factory=dict)


class StoryTracker:
    """Tracks persistent narrative arcs across weeks."""

    def __init__(self, session=None):
        self.session = session
        self.active_arcs: Dict[str, StoryArc] = {}

    def start_arc(self, key: str, *, score: float = 0.0, metadata: Optional[dict] = None) -> StoryArc:
        arc = StoryArc(key=key, week=1, score=score, metadata=metadata or {})
        self.active_arcs[key] = arc
        return arc

    def check_triggers(self, player, stats: Dict[str, float]) -> Optional[str]:
        """Evaluate whether a new arc should begin.

        Returns an optional narrative string to surface to the player/UI.
        """

        recent_avg = stats.get("recent_avg") if stats else None
        if recent_avg is not None and recent_avg < 0.200 and "slump_arc" not in self.active_arcs:
            self.start_arc("slump_arc", score=-5)
            return "Bats feel heavy. Club whispers turn into murmurs about your skid."
        return None

    def advance_arcs(self, player) -> Dict[str, str]:
        """Advance active arcs and return any triggered beat descriptions."""

        beats: Dict[str, str] = {}
        for key, arc in list(self.active_arcs.items()):
            arc.week += 1
            if key == "slump_arc":
                if arc.week == 2:
                    beats[key] = "Week 2: Rumblings grow louder. Teammates steal glances during BP."
                elif arc.week == 3:
                    beats[key] = "Week 3: Coach kills the lights and rolls film—slow-mo swings under harsh fluorescents."
                elif arc.week > 3:
                    beats[key] = "The slump story cools… for now. Focus shifts to the next series."
                    self.active_arcs.pop(key, None)
        return beats
*** End Patch