"""
Universal UI renderer system for CLI screens.
Provides reusable building blocks to render consistent layouts for
player profiles, scouting pages, team reports, match summaries,
menus, pop-ups, and cutscenes.
"""
from __future__ import annotations

from typing import List, Optional

from ui.ui_display import Colour, clear_screen

SCREEN_WIDTH = 78


# Core lines and bars -------------------------------------------------
class UILine:
    @staticmethod
    def thick() -> str:
        return "=" * SCREEN_WIDTH

    @staticmethod
    def thin() -> str:
        return "-" * SCREEN_WIDTH

    @staticmethod
    def divider(text: str = "") -> str:
        txt = f" {text} " if text else ""
        left = "-" * 2
        right = "-" * (SCREEN_WIDTH - 2 - len(txt))
        return left + txt + right


class UIBar:
    BAR_WIDTH = 18

    @staticmethod
    def color_for_value(value: Optional[int]) -> str:
        if value is None:
            return Colour.RESET
        if value < 50:
            return Colour.RED
        if value < 70:
            return Colour.YELLOW
        if value < 90:
            return Colour.CYAN
        return Colour.GREEN

    @staticmethod
    def bar(value: Optional[int]) -> str:
        if value is None:
            return Colour.RED + ("?" * UIBar.BAR_WIDTH) + Colour.RESET
        clamped = max(0, min(100, value))
        filled = int((clamped / 100) * UIBar.BAR_WIDTH)
        empty = UIBar.BAR_WIDTH - filled
        col = UIBar.color_for_value(clamped)
        return col + ("#" * filled) + ("-" * empty) + Colour.RESET


# Containers ---------------------------------------------------------
class UIContainer:
    """Full width block with optional title."""

    def __init__(self, title: str = "", content: Optional[List[str]] = None) -> None:
        self.title = title
        self.content = content or []

    def render(self) -> List[str]:
        lines: List[str] = []
        lines.append(UILine.thick())
        if self.title:
            lines.append(f"| {self.title.center(SCREEN_WIDTH - 4)} |")
            lines.append(UILine.thin())
        for line in self.content:
            lines.append(f"| {line.ljust(SCREEN_WIDTH - 4)} |")
        lines.append(UILine.thick())
        return lines


class UISection:
    """Named block of text."""

    def __init__(self, header: str, body: List[str]) -> None:
        self.header = header
        self.body = body

    def render(self) -> List[str]:
        lines = []
        lines.append("")
        lines.append(f"-- {self.header} --")
        lines.extend(self.body)
        return lines


class UIList:
    """Simple vertical list."""

    def __init__(self, items: List[str]) -> None:
        self.items = items

    def render(self) -> List[str]:
        return [f" * {item}" for item in self.items]


class UIGrid:
    """Two-column stat grid with bars."""

    def __init__(self, rows: List[tuple]) -> None:
        self.rows = rows

    def render(self) -> List[str]:
        out: List[str] = []
        for label, value, delta in self.rows:
            bar = UIBar.bar(value)
            arrow = " " if delta is None else ("^" if delta > 0 else "v" if delta < 0 else "-")
            value_txt = "--" if value is None else f"{value:>3}"
            out.append(f"{label:<14} {bar}  {value_txt} {arrow}")
        return out


class UIPanel:
    """Bordered panel with title."""

    def __init__(self, title: str, lines: List[str]) -> None:
        self.title = title
        self.lines = lines

    def render(self) -> List[str]:
        width = SCREEN_WIDTH
        out: List[str] = []
        out.append("+" + "-" * (width - 2) + "+")
        out.append(f"| {self.title.center(width - 4)} |")
        out.append("+" + "-" * (width - 2) + "+")
        for line in self.lines:
            out.append(f"| {line.ljust(width - 4)} |")
        out.append("+" + "-" * (width - 2) + "+")
        return out


class UIPage:
    """Orchestrates blocks into a page."""

    def __init__(self) -> None:
        self.blocks: List[List[str]] = []

    def add_block(self, lines: List[str]) -> None:
        self.blocks.append(lines)

    def render(self) -> None:
        clear_screen()
        for block in self.blocks:
            for line in block:
                print(line)
        print("")


# Helpers ------------------------------------------------------------
def ui_paragraph(text: str, width: int = SCREEN_WIDTH) -> List[str]:
    """Wrap a long string into lines."""

    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width - 4:
            lines.append(current)
            current = word
        else:
            current = word if not current else f"{current} {word}"
    if current:
        lines.append(current)
    return lines


def ui_card(name: str, subtitle: str, right_text: str = "") -> List[str]:
    """Small header card."""

    width = SCREEN_WIDTH
    out: List[str] = []
    out.append("+" + "-" * (width - 2) + "+")
    out.append(f"| {name.ljust(width - 4)} |")
    out.append(f"| {subtitle.ljust(width - 4)} |")
    if right_text:
        out.append(f"| {right_text.ljust(width - 4)} |")
    out.append("+" + "-" * (width - 2) + "+")
    return out


__all__ = [
    "SCREEN_WIDTH",
    "UILine",
    "UIBar",
    "UIContainer",
    "UISection",
    "UIList",
    "UIGrid",
    "UIPanel",
    "UIPage",
    "ui_paragraph",
    "ui_card",
]
