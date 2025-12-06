"""
Core CLI UI primitives: theming, colours, bars, simple animations.
Lightweight and portable; wraps existing ui_display when available.
"""
from __future__ import annotations

import sys
import time
from typing import Dict, List, Optional

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

    def clear_screen():
        print("\033c", end="")

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
def typewriter(text: str, delay: float = 0.015, end: str = "\n") -> None:
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(end)
    sys.stdout.flush()


def fill_bar_animate(target_value: int, *, max_value: int = 100, theme_name: str = DEFAULT_THEME, width: int = BAR_WIDTH, speed: float = 0.01) -> str:
    target = max(0, min(max_value, int(target_value)))
    target_filled = int((target / max_value) * width)
    for i in range(0, target_filled + 1):
        filled = i
        empty = width - filled
        col = color_for_value(int((i / width) * max_value), theme_name)
        sys.stdout.write("\r" + col + "█" * filled + "░" * empty + Colour.RESET)
        sys.stdout.flush()
        time.sleep(speed)
    sys.stdout.write("\n")
    return colored_bar(target, max_value, theme_name)


def slide_in_panel(lines: List[str], *, width: int = 78, delay: float = 0.004) -> None:
    max_pad = width
    for pad in range(max_pad, -1, -4):
        clear_screen()
        for line in lines:
            print(" " * pad + line)
        time.sleep(delay)
    for line in lines:
        print(line)


def reveal_lines(lines: List[str], delay: float = 0.08) -> None:
    for line in lines:
        print(line)
        time.sleep(delay)


# Panels --------------------------------------------------------------
def panel(title: str, body_lines: List[str], *, width: int = 78, theme: Optional[str] = None) -> None:
    th = choose_theme(theme)
    deco = th["decor"] * width
    print(deco)
    print(f"{th['accent']}{title.center(width)}{Colour.RESET}")
    print(deco)
    for line in body_lines:
        print(line)
    print(deco)


def tick_pause(sec: float = 0.6) -> None:
    time.sleep(sec)


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
    "BAR_WIDTH",
    "THEMES",
    "DEFAULT_THEME",
]
