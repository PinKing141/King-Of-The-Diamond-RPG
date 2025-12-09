"""
Core CLI UI primitives: theming, colours, bars, simple animations.
Lightweight and portable; wraps existing ui_display when available.
"""
from __future__ import annotations

import sys
import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from ui.ui_display import Colour, clear_screen
except Exception:  # fallback for portability
    class Colour:  # type: ignore
        RESET = "\033[0m"
        RED = "\033[31m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        BLUE = "\033[34m"
        MAG = "\033[35m"
        CYAN = "\033[36m"
        WHITE = "\033[97m"
        BOLD = "\033[1m"

    def clear_screen(io=None):
        # Minimal fallback: emit clear escape via IO/log when ui_display is missing
        try:
            if io and hasattr(io, "log"):
                io.log("[clear_screen]")
                return
        except Exception:
            pass
        _emit("\033c", io=io, end="", flush=True)


def _emit(message: str = "", *, io=None, end: str = "\n", flush: bool = False) -> None:
    """Route UI output through IOInterface when available, else logging/stdout."""

    if io and hasattr(io, "log"):
        try:
            io.log(message)
            return
        except Exception:
            pass
    try:
        logger.info(message)
    except Exception:
        pass
    sys.stdout.write(message + end)
    if flush:
        sys.stdout.flush()

# Ensure required colour attrs exist even if ui_display is missing some.
for _missing, _fallback in {
    "WHITE": "\033[97m",
    "MAG": "\033[35m",
}.items():
    if not hasattr(Colour, _missing):
        setattr(Colour, _missing, _fallback)

# Themes --------------------------------------------------------------
THEMES: Dict[str, Dict[str, str]] = {
    "clean": {
        "accent": Colour.CYAN,
        "muted": Colour.WHITE,
        "danger": Colour.RED,
        "good": Colour.GREEN,
        "warn": Colour.YELLOW,
        "decor": "═",
    },
    "anime": {
        "accent": Colour.MAG,
        "muted": Colour.WHITE,
        "danger": Colour.RED,
        "good": Colour.GREEN,
        "warn": Colour.YELLOW,
        "decor": "☆",
    },
    "persona": {
        "accent": Colour.CYAN + Colour.BOLD if hasattr(Colour, "BOLD") else Colour.CYAN,
        "muted": Colour.WHITE,
        "danger": Colour.RED,
        "good": Colour.GREEN,
        "warn": Colour.YELLOW,
        "decor": "■",
    },
    "legacy": {
        "accent": Colour.BLUE,
        "muted": Colour.WHITE,
        "danger": Colour.RED,
        "good": Colour.GREEN,
        "warn": Colour.YELLOW,
        "decor": "#",
    },
}

DEFAULT_THEME = "persona"
BAR_WIDTH = 18


def choose_theme(name: Optional[str]) -> Dict[str, str]:
    return THEMES.get((name or "").lower(), THEMES[DEFAULT_THEME])


def safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


# Bars ----------------------------------------------------------------
def color_for_value(value: Optional[int], theme_name: Optional[str] = None) -> str:
    theme = choose_theme(theme_name)
    if value is None:
        return theme["muted"]
    v = safe_int(value)
    if v < 50:
        return theme["danger"]
    if v < 70:
        return theme["warn"]
    if v < 90:
        return theme["accent"]
    return theme["good"]


def colored_bar(value: Optional[int], max_value: int = 100, theme_name: Optional[str] = None) -> str:
    width = BAR_WIDTH
    v = 0 if value is None else max(0, min(max_value, safe_int(value)))
    filled = int((v / max_value) * width)
    empty = width - filled
    col = color_for_value(value, theme_name)
    return f"{col}{'█' * filled}{'░' * empty}{Colour.RESET}"


def simple_bar(value: Optional[int], max_value: int = 100, width: int = BAR_WIDTH) -> str:
    if value is None:
        return " " * width
    v = max(0, min(max_value, safe_int(value)))
    filled = int((v / max_value) * width)
    return "█" * filled + "▒" * (width - filled)


# Animations ----------------------------------------------------------
def typewriter(text: str, delay: float = 0.015, end: str = "\n", *, io=None) -> None:
    for ch in text:
        _emit(ch, io=io, end="", flush=True)
        time.sleep(delay)
    _emit(end, io=io, end="", flush=True)


def fill_bar_animate(target_value: int, *, max_value: int = 100, theme_name: str = DEFAULT_THEME, width: int = BAR_WIDTH, speed: float = 0.01, io=None) -> str:
    target = max(0, min(max_value, int(target_value)))
    target_filled = int((target / max_value) * width)
    for i in range(0, target_filled + 1):
        filled = i
        empty = width - filled
        col = color_for_value(int((i / width) * max_value), theme_name)
        _emit("\r" + col + "█" * filled + "░" * empty + Colour.RESET, io=io, end="", flush=True)
        time.sleep(speed)
    _emit("\n", io=io, end="", flush=True)
    return colored_bar(target, max_value, theme_name)


def slide_in_panel(lines: List[str], *, width: int = 78, delay: float = 0.004, io=None) -> None:
    max_pad = width
    for pad in range(max_pad, -1, -4):
        clear_screen()
        for line in lines:
            _emit(" " * pad + line, io=io)
        time.sleep(delay)
    for line in lines:
        _emit(line, io=io)


def reveal_lines(lines: List[str], delay: float = 0.08, *, io=None) -> None:
    for line in lines:
        _emit(line, io=io)
        time.sleep(delay)


# Panels --------------------------------------------------------------
def panel(title: str, body_lines: List[str], *, width: int = 78, theme: Optional[str] = None, io=None) -> None:
    th = choose_theme(theme)
    deco = th["decor"] * width
    _emit(deco, io=io)
    _emit(f"{th['accent']}{title.center(width)}{Colour.RESET}", io=io)
    _emit(deco, io=io)
    for line in body_lines:
        _emit(line, io=io)
    _emit(deco, io=io)


def tick_pause(sec: float = 0.6) -> None:
    time.sleep(sec)


# Navigation helpers -------------------------------------------------
def show_page(fn, *args, clear: bool = True, **kwargs):
    """Central place to clear the screen before rendering a new view."""
    if clear:
        clear_screen()
    return fn(*args, **kwargs)


__all__ = [
    "Colour",
    "clear_screen",
    "choose_theme",
    "color_for_value",
    "colored_bar",
    "simple_bar",
    "typewriter",
    "fill_bar_animate",
    "slide_in_panel",
    "reveal_lines",
    "panel",
    "tick_pause",
    "show_page",
    "BAR_WIDTH",
    "THEMES",
    "DEFAULT_THEME",
]
