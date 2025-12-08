from __future__ import annotations

from typing import List, Optional, Protocol


class IOInterface(Protocol):
    """Abstract IO surface so game logic can stay UI-agnostic."""

    def log(self, message: str, *, level: str = "info") -> None:
        """Emit a log line for the user."""
        ...

    def prompt(self, prompt: str, *, options: Optional[List[str]] = None) -> str:
        """Request input from the user, optionally constraining valid options."""
        ...

    def clear(self) -> None:
        """Clear the primary output surface."""
        ...

    def wait(self, seconds: float) -> None:
        """Delay execution for pacing effects without hard-coding time.sleep."""
        ...
