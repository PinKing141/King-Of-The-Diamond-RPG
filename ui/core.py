from __future__ import annotations

import os
import sys
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
        input_fn: Optional[Callable[..., Optional[str]]] = None,
    ) -> Optional[str]:
        """Render a numbered/keyed menu and return the selected value."""

        default_choice = next((opt for opt in options if opt.key == ""), None)
        preface_lines = list(preface or [])
        status_msg = ""

        def _invoke_input_fn(submitted: str) -> Optional[str]:
            if input_fn is None:
                return submitted
            try:
                return input_fn(prompt_text, raw_override=submitted)
            except TypeError:
                return input_fn(prompt_text)

        def _resolve_choice(choice: str) -> Optional[str]:
            nonlocal status_msg
            if allow_quit and choice.lower() == "q":
                return None
            if not choice and default_choice:
                if not default_choice.enabled:
                    status_msg = "Option locked."
                    return None
                return default_choice.resolved_value()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    opt = options[idx]
                    if not opt.enabled:
                        status_msg = "Option locked."
                        return None
                    return opt.resolved_value()
            for opt in options:
                if choice.lower() == opt.key.lower():
                    if not opt.enabled:
                        status_msg = "Option locked."
                        return None
                    return opt.resolved_value()
            status_msg = "Invalid choice."
            return None

        def _first_enabled_index() -> int:
            if default_choice and default_choice.enabled:
                try:
                    return next(i for i, opt in enumerate(options) if opt.key == "")
                except StopIteration:
                    pass
            for i, opt in enumerate(options):
                if opt.enabled:
                    return i
            return 0

        def _move_index(current: int, delta: int) -> int:
            next_idx = current
            for _ in range(len(options)):
                next_idx = (next_idx + delta) % len(options)
                if options[next_idx].enabled:
                    return next_idx
            return current

        def _read_keypress():
            if os.name == "nt":
                import msvcrt

                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    return "ENTER", None
                if ch == "\x1b":
                    return "ESC", None
                if ch in ("\x08",):
                    return "BACKSPACE", None
                if ch in ("\xe0", "\x00"):
                    nxt = msvcrt.getwch()
                    mapping = {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT"}
                    return mapping.get(nxt, "CHAR"), None
                return "CHAR", ch
            else:
                try:
                    import tty
                    import termios
                except ImportError:
                    return "CHAR", sys.stdin.read(1)

                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    ch = sys.stdin.read(1)
                    if ch in ("\r", "\n"):
                        return "ENTER", None
                    if ch in ("\x7f", "\b"):
                        return "BACKSPACE", None
                    if ch == "\x1b":
                        seq = sys.stdin.read(2)
                        mapping = {"[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT"}
                        return mapping.get(seq, "ESC"), None
                    return "CHAR", ch
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)

        def _render(block_height: int, *, first: bool, pointer_idx: int, buffer: str) -> int:
            if clear_first:
                self.clear()
            else:
                if not first and block_height > 0:
                    sys.stdout.write(f"\033[{block_height}F")
            # Panel border
            self.box(title, [], width=78)
            lines = 3  # panel draws three lines
            for line in preface_lines:
                self.log(line)
                lines += 1
            for idx, opt in enumerate(options, start=1):
                pointer = ">" if (idx - 1) == pointer_idx else " "
                key_hint = opt.display_key()
                label = opt.label
                if not opt.enabled:
                    label = f"{Colour.RED}{label} (locked){Colour.RESET}"
                self.log(f"{pointer} [{key_hint or idx}] {label}")
                lines += 1
            if footer:
                self.log("")
                self.log(footer)
                lines += 2
            # Status line (always reserve space for stability when redrawing)
            self.log(status_msg or "")
            lines += 1
            self.log(f"{prompt_text}{buffer}")
            lines += 1
            return lines

        # Arrow-navigation path (opt-in via IO capability + TTY)
        use_raw = bool(getattr(self._io, "supports_raw_input", False) and sys.stdin.isatty())
        if use_raw:
            try:
                buffer = ""
                idx = _first_enabled_index()
                block_height = 0
                first = True
                while True:
                    block_height = _render(block_height, first=first, pointer_idx=idx, buffer=buffer)
                    first = False
                    action, payload = _read_keypress()
                    if action in ("UP", "LEFT"):
                        idx = _move_index(idx, -1)
                        continue
                    if action in ("DOWN", "RIGHT"):
                        idx = _move_index(idx, 1)
                        continue
                    if action == "BACKSPACE":
                        buffer = buffer[:-1]
                        continue
                    if action == "ESC":
                        if allow_quit:
                            return None
                        buffer = ""
                        status_msg = ""
                        continue
                    if action == "CHAR" and payload:
                        buffer += payload
                        continue
                    if action == "ENTER":
                        if buffer.strip():
                            raw_value = buffer.strip()
                            submitted = _invoke_input_fn(raw_value)
                            buffer = ""
                            status_msg = ""
                            if submitted is None:
                                continue
                            choice = str(submitted).strip()
                            resolved = _resolve_choice(choice)
                            if resolved is not None:
                                return resolved
                            continue
                        # No manual buffer: select default if present, else highlighted
                        if default_choice:
                            resolved = _resolve_choice("")
                            if resolved is not None:
                                return resolved
                            if status_msg:
                                continue
                        if not options:
                            return None
                        if not options[idx].enabled:
                            status_msg = "Option locked."
                            continue
                        return options[idx].resolved_value()
            except Exception:
                # On any unexpected error fall back to legacy prompt logic.
                pass

        # Legacy text entry path (non-interactive environments / tests)
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
            resolved = _resolve_choice(choice)
            if resolved is not None:
                return resolved
            if status_msg:
                self.log(status_msg, level="warning")
                status_msg = ""
            else:
                self.log("Invalid choice.")


ui = UI()

__all__ = ["MenuChoice", "UI", "ui", "BAR_WIDTH"]
