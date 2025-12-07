"""
Universal CLI menu framework built on ui_core primitives.
Supports simple numbered selection with optional per-option enablement.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from ui.ui_core import choose_theme, panel, clear_screen, Colour, tick_pause


class MenuOption:
    def __init__(self, key: str, label: str, action: Optional[Callable] = None, enabled: bool = True) -> None:
        self.key = key
        self.label = label
        self.action = action
        self.enabled = enabled


class MenuScreen:
    def __init__(self, title: str, options: List[MenuOption], *, theme: Optional[str] = None, footer: Optional[str] = None) -> None:
        self.title = title
        self.options = options
        self.theme = theme
        self.footer = footer or ""

    def _format_option(self, opt: MenuOption) -> str:
        key = f"[{opt.key}]"
        if not opt.enabled:
            return f" {key:<5} {Colour.RED}{opt.label} (LOCKED){Colour.RESET}"
        return f" {key:<5} {opt.label}"

    def show(self) -> None:
        clear_screen()
        panel(self.title, [], theme=self.theme)
        for opt in self.options:
            print(self._format_option(opt))
        if self.footer:
            print("\n" + self.footer)
        print("\nSelect option by number/key, or press Q to cancel.")

    def run(self):
        while True:
            self.show()
            choice = input("> ").strip()
            if not choice:
                continue
            if choice.lower() == "q":
                return None
            # numeric selection maps to index
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(self.options):
                    opt = self.options[idx]
                    if not opt.enabled:
                        print("Option locked.")
                        tick_pause(0.5)
                        continue
                    if opt.action:
                        return opt.action()
                    return opt.key
            # direct key match
            for opt in self.options:
                if choice.lower() == opt.key.lower():
                    if not opt.enabled:
                        print("Option locked.")
                        tick_pause(0.5)
                        break
                    if opt.action:
                        return opt.action()
                    return opt.key
            print("Invalid choice. Try again.")
            tick_pause(0.4)


__all__ = ["MenuOption", "MenuScreen"]
