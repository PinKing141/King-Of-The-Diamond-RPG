"""Authoritative enums that describe the paced match loop."""
from __future__ import annotations

from enum import Enum, auto


class MatchState(Enum):
    """Fine-grained phases for a single pitch/at-bat cycle."""

    WAITING_FOR_PITCH = auto()
    PITCH_FLIGHT = auto()
    CONTACT_MOMENT = auto()
    PLAY_RESOLUTION = auto()


class EventType(str, Enum):
    """Canonical event names published on the EventBus."""

    MATCH_STATE = "MATCH_STATE_CHANGE"
    PITCH_THROWN = "PITCH_THROWN"
    BATTER_SWUNG = "BATTER_SWUNG"
    STRIKEOUT = "STRIKEOUT"
    PLAY_RESULT = "PLAY_RESULT"
    BATTERS_EYE_PROMPT = "BATTERS_EYE_PROMPT"
    MOMENTUM_SHIFT = "MOMENTUM_SHIFT"


__all__ = ["MatchState", "EventType"]
