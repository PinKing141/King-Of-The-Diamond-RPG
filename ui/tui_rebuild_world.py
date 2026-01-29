"""
Textual UI for rebuild-world confirmation and progress display.
Env flag used: USE_TUI_WORLD_LOADING (shared with world gen overlay).
"""
from __future__ import annotations

from typing import Callable, Optional
import asyncio

TUI_AVAILABLE = False

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, OptionList, Static
    from textual.containers import Container
    from textual.reactive import reactive

    TUI_AVAILABLE = True
except Exception:
    TUI_AVAILABLE = False

SPINNER_FRAMES = ["|", "/", "-", "\\"]


if TUI_AVAILABLE:

    class RebuildWorldApp(App[bool]):
        CSS = """
        Screen { align: center middle; background: #0d1117; }
        #frame { width: 90; height: auto; border: round #58a6ff; padding: 2 3; background: #0b0f14; }
        #title { color: #58a6ff; text-style: bold; height: 2; }
        #status { color: #c9d1d9; }
        #error { color: tomato; }
        """

        status_text = reactive("Are you sure you want to rebuild the world? This deletes the current DB.")
        confirming = reactive(True)
        done = reactive(False)
        success = reactive(False)
        allow_cancel = reactive(True)

        def __init__(self, *, rebuild_fn: Callable[[], bool]):
            super().__init__()
            self.rebuild_fn = rebuild_fn

        def compose(self) -> ComposeResult:
            yield Container(
                Header(show_clock=False),
                Static("REBUILD WORLD", id="title"),
                Static(self.status_text, id="status"),
                OptionList("Yes, rebuild", "No / cancel", id="olist"),
                Static("", id="error"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            self.query_one(OptionList).focus()

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            if not self.confirming:
                return
            if event.option_index == 0:
                self.confirming = False
                self.status_text = "Rebuilding... Please wait."
                self.query_one("#status", Static).update(self.status_text)
                self.query_one(OptionList).visible = False
                self.call_later(self._run_rebuild)
            else:
                self.exit(False)

        async def _run_rebuild(self) -> None:
            # Show spinner while running
            self.set_interval(0.15, self._tick_spinner)
            try:
                res = await asyncio.to_thread(self.rebuild_fn)
                self.success = bool(res)
            except Exception as exc:  # pragma: no cover
                self.query_one("#error", Static).update(f"Failed: {exc}")
                self.success = False
            finally:
                self.done = True
                if self.success:
                    self.status_text = "World rebuild complete. Press Enter to exit."
                else:
                    self.status_text = "World rebuild failed. Press Enter to exit."
                self.query_one("#status", Static).update(self.status_text)

        def _tick_spinner(self) -> None:
            return  # spinner removed

        def on_key(self, event) -> None:
            if not self.done and event.key in {"escape", "q"} and self.allow_cancel:
                self.done = True
                self.success = False
                self.exit(False)
                return
            if self.done:
                self.exit(self.success)


def run_tui_rebuild_world(rebuild_fn: Callable[[], bool]) -> Optional[bool]:
    """Run rebuild with a TUI confirm + spinner. Returns True/False, or None if unavailable."""
    if not TUI_AVAILABLE:
        return None
    app = RebuildWorldApp(rebuild_fn=rebuild_fn)
    return app.run()
