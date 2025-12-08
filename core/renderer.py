from __future__ import annotations

from typing import Protocol

from ui.ui_display import Colour


class Renderer(Protocol):
    """Abstract renderer for styling text output.

    Keeps colour/formatting decisions out of game logic so alternate UIs can
    supply their own assets.
    """

    def colorize(self, message: str, *, style: str = "info") -> str:
        ...

    def header(self, message: str) -> str:
        ...

    def emphasize(self, message: str) -> str:
        ...


class ConsoleRenderer(Renderer):
    """Console renderer that applies ANSI colour codes via ui_display. """

    _STYLES = {
        "error": Colour.FAIL,
        "fail": Colour.FAIL,
        "warning": Colour.WARNING,
        "warn": Colour.WARNING,
        "story": Colour.CYAN,
        "info": "",
        "muted": Colour.dim if hasattr(Colour, "dim") else "",
        "accent": Colour.GREEN,
        "bold": Colour.BOLD,
    }

    def colorize(self, message: str, *, style: str = "info") -> str:
        code = self._STYLES.get(style, "")
        if not code:
            return message
        return f"{code}{message}{Colour.RESET}"

    def header(self, message: str) -> str:
        return f"{Colour.HEADER}{message}{Colour.RESET}"

    def emphasize(self, message: str) -> str:
        return f"{Colour.BOLD}{message}{Colour.RESET}"
