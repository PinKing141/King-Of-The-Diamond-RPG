from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from core.io_interface import IOInterface
from ui.ui_core import BAR_WIDTH, DEFAULT_THEME, choose_theme, colored_bar, panel
from ui.ui_display import Colour, clear_screen


@dataclass
class MenuChoice:
    """Represents a single menu entry understood by the UI abstraction layer."""

    key: str
    label: str
    value: Optional[str] = None
    enabled: bool = True
    hint: Optional[str] = None

    def resolved_value(self) -> str:
        return self.value if self.value is not None else self.key

    def display_key(self) -> str:
        if self.hint:
            return self.hint
        if self.key == "":
            return "Enter"
        return self.key


class _FallbackIO(IOInterface):
    """Minimal IOInterface implementation used when no IO is provided."""

    def log(self, message: str, *, level: str = "info") -> None:
        print(message)

    def prompt(self, prompt: str, *, options: Optional[List[str]] = None) -> str:
        while True:
            try:
                response = input(prompt)
            except (EOFError, KeyboardInterrupt):
                return ""
            if not options or response in options:
                return response
            print(f"Please enter one of: {', '.join(options)}")

    def clear(self) -> None:
        clear_screen()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


class UI:
    """Unified UI abstraction usable by CLI renderers and future GUI adapters."""

    def __init__(self, io: Optional[IOInterface] = None, *, theme: str = DEFAULT_THEME) -> None:
        self._io = io or _FallbackIO()
        self.theme = theme or DEFAULT_THEME

    def with_io(self, io: IOInterface) -> "UI":
        return UI(io, theme=self.theme)

    def with_theme(self, theme: Optional[str]) -> "UI":
        return UI(self._io, theme=theme or self.theme)

    def log(self, message: str, *, level: str = "info") -> None:
        self._io.log(message, level=level)

    def print(self, message: str, *, level: str = "info") -> None:
        self.log(message, level=level)

    def stream(self, message: str, *, end: str = "\n") -> None:
        """Progress-friendly writer that preserves partial lines for CLI."""
        if end == "\n":
            self.log(message)
            return
        try:
            print(message, end=end)
        except Exception:
            self.log(message)

    def prompt(
        self,
        prompt: str,
        *,
        options: Optional[Sequence[str]] = None,
        default: str = "",
        input_fn: Optional[Callable[[str], Optional[str]]] = None,
    ) -> str:
        if input_fn is not None:
            try:
                response = input_fn(prompt)
            except (EOFError, KeyboardInterrupt):
                return default
            return default if response is None else response
        response = self._io.prompt(prompt, options=list(options) if options is not None else None)
        return default if response is None else response

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        fallback = "y" if default else "n"
        response = self.prompt(prompt, default=fallback)
        return response.strip().lower().startswith("y")

    def clear(self) -> None:
        try:
            self._io.clear()
        except Exception:
            clear_screen()

    def wait(self, seconds: float) -> None:
        try:
            self._io.wait(seconds)
        except Exception:
            time.sleep(seconds)

    def bar(self, value: Optional[int], *, max_value: int = 100) -> str:
        return colored_bar(value, max_value=max_value, theme_name=self.theme)

    def box(self, title: str, body: Sequence[str], *, width: int = 78) -> None:
        panel(title, list(body), width=width, theme=self.theme)

    def header(self, title: str, subtitle: Optional[str] = None, *, width: int = 68) -> None:
        theme = choose_theme(self.theme)
        deco = theme["decor"] * width
        self.log(f"{theme['accent']}{deco}{Colour.RESET}")
        self.log(f"{theme['accent']}{title.center(width)}{Colour.RESET}")
        if subtitle:
            self.log(f"{theme['muted']}{subtitle.center(width)}{Colour.RESET}")
        self.log(f"{theme['accent']}{deco}{Colour.RESET}")

    def menu(
        self,
        title: str,
        options: Sequence[MenuChoice],
        *,
        preface: Optional[Sequence[str]] = None,
        footer: Optional[str] = None,
        prompt_text: str = "> ",
        allow_quit: bool = False,
        clear_first: bool = True,
        input_fn: Optional[Callable[[str], Optional[str]]] = None,
    ) -> Optional[str]:
        """Render a numbered/keyed menu and return the selected value."""

        default_choice = next((opt for opt in options if opt.key == ""), None)
        preface_lines = list(preface or [])
        while True:
            if clear_first:
                self.clear()
            self.box(title, [], width=78)
            for line in preface_lines:
                self.log(line)
            for idx, opt in enumerate(options, start=1):
                key_hint = opt.display_key()
                label = opt.label
                if not opt.enabled:
                    label = f"{Colour.RED}{label} (locked){Colour.RESET}"
                self.log(f" [{key_hint or idx}] {label}")
            if footer:
                self.log("")
                self.log(footer)

            raw = self.prompt(prompt_text, input_fn=input_fn)
            if raw is None:
                return None
            choice = raw.strip()
            if allow_quit and choice.lower() == "q":
                return None
            if not choice and default_choice:
                if not default_choice.enabled:
                    self.log("Option locked.", level="warning")
                    continue
                return default_choice.resolved_value()
            # numeric selection
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    opt = options[idx]
                    if not opt.enabled:
                        self.log("Option locked.", level="warning")
                        continue
                    return opt.resolved_value()
            # direct key match
            for opt in options:
                if choice.lower() == opt.key.lower():
                    if not opt.enabled:
                        self.log("Option locked.", level="warning")
                        break
                    return opt.resolved_value()
            self.log("Invalid choice.")


ui = UI()

__all__ = ["MenuChoice", "UI", "ui", "BAR_WIDTH"]
