"""
Textual weekly command menu (next-week, scouting, save, smart-sim, quit).
Falls back to console when Textual is unavailable.
"""
from __future__ import annotations

from typing import Optional

TUI_AVAILABLE = False

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container
    from textual.widgets import Header, Footer, OptionList, Static

    TUI_AVAILABLE = True
except Exception:
    TUI_AVAILABLE = False


if TUI_AVAILABLE:

    class WeeklyMenuApp(App[str]):
        CSS = """
        Screen {
            align: center middle;
            background: #0d1117;
        }
        #frame {
            width: 70;
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
            width: 100%;
        }
        """

        def __init__(self, *, year: int, week: int, month: int) -> None:
            super().__init__()
            self.year = year
            self.week = week
            self.month = month
            self.choice: Optional[str] = None
            self._options = [
                ("Next Week", "NEXT_WEEK"),
                ("Scouting / Roster", "SCOUT"),
                ("Save Game", "SAVE"),
                ("Smart Sim (Delegate Weeks)", "SMART_SIM"),
                ("Quit to Menu", "QUIT"),
            ]

        def compose(self) -> ComposeResult:
            subtitle = f"Year {self.year} | Week {self.week} | Month {self.month}"
            yield Container(
                Header(show_clock=False),
                Static("Weekly Command Menu", id="title"),
                Static(subtitle, id="subtitle"),
                OptionList(*(f"{label}" for label, _ in self._options), id="olist"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            self.query_one(OptionList).focus()

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            idx = event.option_index
            if 0 <= idx < len(self._options):
                self.choice = self._options[idx][1]
                self.exit(self.choice)

        def action_quit(self) -> None:
            self.choice = "QUIT"
            self.exit(self.choice)


def run_tui_weekly_menu(*, year: int, week: int, month: int) -> Optional[str]:
    if not TUI_AVAILABLE:
        return None
    app = WeeklyMenuApp(year=year, week=week, month=month)
    return app.run()
