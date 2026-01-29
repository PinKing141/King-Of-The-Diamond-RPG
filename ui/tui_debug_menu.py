"""
Textual-based Debug Master Menu. Mirrors the existing debug options and returns
the selected command token ("1"-"8" or "0"/"q").
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

TUI_AVAILABLE = False

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, OptionList, Static
    from textual.containers import Container

    TUI_AVAILABLE = True
except Exception:
    TUI_AVAILABLE = False
    if TYPE_CHECKING:
        from textual.app import App, ComposeResult  # type: ignore
        from textual.widgets import Header, Footer, OptionList, Static  # type: ignore
        from textual.containers import Container  # type: ignore
    else:
        class App:  # stub types for linters
            def __init__(self, *_, **__): ...
            def exit(self, *_): ...

        class ComposeResult: ...

        class _WidgetStub:
            def __init__(self, *_, **__): ...

        Header = Footer = OptionList = Static = Container = _WidgetStub


OPTIONS = [
    ("Set date (year/month/week)", "1"),
    ("Fast set all player stats (value)", "2"),
    ("Add ability points / trust / morale / fatigue", "3"),
    ("Jump to key weeks (15 qualifiers / 48 spring)", "4"),
    ("Quick exhibition vs school id", "5"),
    ("Give max stats (99) + full stamina", "6"),
    ("Play full match vs school id (turn-based)", "7"),
    ("Edit pitch shape / release / extension (pitchers)", "8"),
    ("Exit debug menu", "0"),
]


if TUI_AVAILABLE:

    class DebugMenuApp(App[str]):
        CSS = """
        Screen {
            align: center middle;
            background: #0d1117;
        }
        #frame {
            width: 90;
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

        def __init__(self, *, subtitle: str = "") -> None:
            super().__init__()
            self.subtitle_text = subtitle
            self.choice: Optional[str] = None

        def compose(self) -> ComposeResult:
            yield Container(
                Header(show_clock=False),
                Static("DEBUG MASTER MODE", id="title"),
                Static(self.subtitle_text, id="subtitle"),
                OptionList(*(label for label, _ in OPTIONS), id="olist"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            self.query_one(OptionList).focus()

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            idx = event.option_index
            if 0 <= idx < len(OPTIONS):
                self.choice = OPTIONS[idx][1]
                self.exit(self.choice)

        def action_quit(self) -> None:
            self.choice = "0"
            self.exit(self.choice)


def run_tui_debug_menu(subtitle: str = "") -> Optional[str]:
    """Launch the Textual debug menu. Returns choice token or None if unavailable."""
    if not TUI_AVAILABLE:
        return None
    app = DebugMenuApp(subtitle=subtitle)
    return app.run()
