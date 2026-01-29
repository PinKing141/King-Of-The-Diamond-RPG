"""Shared battery negotiation data structures."""

from dataclasses import dataclass


@dataclass
class NegotiatedPitchCall:
    pitch: object
    location: str
    intent: str = "Normal"
    shakes: int = 0
    trust: int = 50
    forced: bool = False
    sync: float = 0.0
    perfect_location: bool = False  # Synchronized Pitch: guarantees paint once per game
