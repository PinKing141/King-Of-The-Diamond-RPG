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
    PITCH_MINIGAME_TRIGGER = "PITCH_MINIGAME_TRIGGER"
    PITCH_MINIGAME_RESOLVE = "PITCH_MINIGAME_RESOLVE"
    BATTERY_SIGN_CALLED = "BATTERY_SIGN_CALLED"
    BATTERY_SHAKE = "BATTERY_SHAKE"
    BATTERY_FORCED_CALL = "BATTERY_FORCED_CALL"
    BASERUN_THREAT = "BASERUN_THREAT"
    BASERUN_STEAL = "BASERUN_STEAL"
    BASERUN_PICKOFF = "BASERUN_PICKOFF"
    OFFENSE_CALLS_SQUEEZE = "OFFENSE_CALLS_SQUEEZE"
    PSYCHOLOGY_SHIFT = "PSYCHOLOGY_SHIFT"
    DUGOUT_CHATTER = "DUGOUT_CHATTER"
    RIVAL_CUT_IN = "RIVAL_CUT_IN"


__all__ = ["MatchState", "EventType"]
