"""
Reusable Textual panel for displaying scrollable text blocks (read-only).
"""
from __future__ import annotations

from typing import Iterable, Optional, TYPE_CHECKING

TUI_AVAILABLE = False

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, Static, ScrollView
    from textual.containers import Container

    TUI_AVAILABLE = True
except Exception:
    TUI_AVAILABLE = False
    if TYPE_CHECKING:
        from textual.app import App, ComposeResult  # type: ignore
        from textual.widgets import Header, Footer, Static, ScrollView  # type: ignore
        from textual.containers import Container  # type: ignore
    else:
        class App:  # stubs for static analysis
            def __init__(self, *_, **__): ...
            def exit(self, *_): ...

        class ComposeResult: ...

        class _WidgetStub:
            def __init__(self, *_, **__): ...

        Header = Footer = Static = ScrollView = Container = _WidgetStub


if TUI_AVAILABLE:

    class TextPanelApp(App[bool]):
        CSS = """
        Screen {
            align: center middle;
            background: #0d1117;
        }
        #frame {
            width: 100;
            height: 90%;
            border: round #58a6ff;
            padding: 1 2;
            background: #0b0f14;
        }
        #title {
            color: #58a6ff;
            text-style: bold;
            height: 2;
        }
        #body {
            color: #c9d1d9;
        }
        """

        def __init__(self, *, title: str, lines: Iterable[str]):
            super().__init__()
            self.title_text = title
            self.lines = list(lines)

        def compose(self) -> ComposeResult:
            yield Container(
                Header(show_clock=False),
                Static(self.title_text, id="title"),
                ScrollView(Static("\n".join(self.lines), id="body")),
                Footer(),
                id="frame",
            )

        def on_key(self, event) -> None:
            if event.key in {"escape", "q"}:
                self.exit(True)


def run_tui_panel(*, title: str, lines: Iterable[str]) -> Optional[bool]:
    """Display a scrollable text panel. Returns True on exit, None if unavailable."""
    if not TUI_AVAILABLE:
        return None
    app = TextPanelApp(title=title, lines=lines)
    return app.run()
