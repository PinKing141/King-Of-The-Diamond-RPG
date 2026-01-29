"""
Simple Textual yes/no confirmation dialog.
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
        class App:  # minimal stubs for linters
            def __init__(self, *_, **__): ...
            def exit(self, *_): ...

        class ComposeResult: ...

        class _WidgetStub:
            def __init__(self, *_, **__): ...

        Header = Footer = OptionList = Static = Container = _WidgetStub


if TUI_AVAILABLE:

    class ConfirmApp(App[bool]):
        CSS = """
        Screen { align: center middle; background: #0d1117; }
        #frame { width: 80; height: auto; border: round #58a6ff; padding: 1 2; background: #0b0f14; }
        #title { color: #58a6ff; text-style: bold; height: 2; }
        OptionList { width: 100%; }
        """

        def __init__(self, prompt: str):
            super().__init__()
            self.prompt = prompt
            self.result: Optional[bool] = None

        def compose(self) -> ComposeResult:
            yield Container(
                Header(show_clock=False),
                Static(self.prompt, id="title"),
                OptionList("Yes", "No", id="olist"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            self.query_one(OptionList).focus()

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            if event.option_index == 0:
                self.result = True
            else:
                self.result = False
            self.exit(self.result)

        def action_quit(self) -> None:
            self.result = False
            self.exit(self.result)


def run_tui_confirm(prompt: str) -> Optional[bool]:
    """Return True/False on selection, None if Textual unavailable."""
    if not TUI_AVAILABLE:
        return None
    app = ConfirmApp(prompt)
    return app.run()
