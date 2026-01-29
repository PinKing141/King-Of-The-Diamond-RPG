"""
Optional Textual-based main menu. Keeps logic parity with the console menu
and returns the same choice tokens ("1"-"5"). Only used when explicitly enabled.
"""
from __future__ import annotations

import os
from typing import Optional

TUI_AVAILABLE = False

try:
    from textual.app import App, ComposeResult
    from textual.widgets import OptionList, Static
    from textual.containers import Container
    from textual.reactive import reactive

    TUI_AVAILABLE = True
except Exception:
    # Textual not installed; fallback handled by caller.
    TUI_AVAILABLE = False


if TUI_AVAILABLE:

    class _MainMenuApp(App[None]):
        CSS = """
        Screen {
            align: center middle;
            background: #0d1117;
        }
        #frame {
            width: 68;
            height: auto;
            border: round #58a6ff;
            padding: 1 2;
            background: #0b0f14;
        }
        #title {
            color: #58a6ff;
            text-style: bold;
            height: 2;
        }
        #subtitle {
            color: #8b949e;
            height: 1;
        }
        OptionList {
            border: blank;
            height: auto;
            width: 100%;
        }
        """

        BINDINGS = [("q", "quit", "Quit")]

        def __init__(self, *, player_info: str, has_save: bool) -> None:
            super().__init__()
            self.player_info = player_info
            self.has_save = has_save
            self.choice: Optional[str] = None
            self._options: list[tuple[str, str]] = []
            self.selected_label = reactive("")

        def _build_options(self) -> list[tuple[str, str]]:
            opts = [
                ("Continue / Start Season", "1"),
                ("Load Game", "2"),
                ("New Career (Same World)", "3"),
                ("Rebuild World (Fresh Generation)", "4"),
                ("Quit", "5"),
            ]
            if not self.has_save:
                opts[0] = ("Start Season (no save found)", "1")
            return opts

        def compose(self) -> ComposeResult:
            self._options = self._build_options()
            yield Container(
                Static("KING OF THE DIAMOND", id="title"),
                Static(self.player_info, id="subtitle"),
                OptionList(
                    *(f"{idx+1}. {label}" for idx, (label, _) in enumerate(self._options)),
                    id="menu",
                ),
                id="frame",
            )

        def on_mount(self) -> None:
            opt_list = self.query_one(OptionList)
            opt_list.focus()

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            idx = event.option_index
            if idx < 0 or idx >= len(self._options):
                return
            self.choice = self._options[idx][1]
            self.exit()

        def action_quit(self) -> None:
            self.choice = "5"
            self.exit()


def run_tui_main_menu(*, player_info: str, has_save: bool) -> Optional[str]:
    """
    Show the Textual main menu and return the selected choice token,
    or None if TUI is unavailable or the user cancelled.
    """
    if not TUI_AVAILABLE:
        return None

    app = _MainMenuApp(player_info=player_info, has_save=has_save)
    app.run()
    return app.choice
