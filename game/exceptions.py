"""
Custom exception definitions for King of the Diamond.
"""

class KoshienException(Exception):
    """Base class for all game-specific errors."""


class SaveError(KoshienException):
    """Base class for save/load related errors."""


class SaveCorruptError(SaveError):
    """Raised when a save file exists but cannot be read or is missing data."""


class SaveNotFoundError(SaveError):
    """Raised when attempting to load a slot that does not exist."""


class ScheduleError(KoshienException):
    """Raised when the weekly scheduler fails to generate valid events."""


class AssetError(KoshienException):
    """Raised when critical data assets (names, cities) are missing."""


class GameStateError(KoshienException):
    """Raised when the game state is inconsistent (e.g. missing active player)."""
