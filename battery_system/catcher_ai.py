"""Legacy shim that exposes the new catcher AI implementation."""

from game.catcher_ai import (
    CatcherMemory,
    PitchCall,
    generate_catcher_sign,
    get_or_create_catcher_memory,
)

__all__ = [
    "CatcherMemory",
    "PitchCall",
    "generate_catcher_sign",
    "get_or_create_catcher_memory",
]