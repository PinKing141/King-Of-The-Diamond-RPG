"""
Textual overlay for world generation. Runs the generation function in a thread
and shows a minimal progress/spinner until completion.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

TUI_AVAILABLE = False

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container
    from textual.widgets import Footer, Header, Static
    from textual.reactive import reactive

    TUI_AVAILABLE = True
except Exception:
    TUI_AVAILABLE = False

SPINNER_FRAMES = ["|", "/", "-", "\\"]


if TUI_AVAILABLE:

    class WorldGenApp(App[bool]):
        CSS = """
        Screen {
            align: center middle;
            background: #0d1117;
        }
        #frame {
            width: 80;
            height: auto;
            border: round #58a6ff;
            padding: 2 3;
            background: #0b0f14;
        }
        #title {
            color: #58a6ff;
            text-style: bold;
            height: 2;
        }
        #status {
            color: #c9d1d9;
            height: auto;
        }
        #error {
            color: tomato;
        }
        """

        status_text = reactive("Starting world generation...")
        done = reactive(False)
        success = reactive(False)
        progress_lines = reactive(list)
        total_pref = reactive(0)

        def __init__(self, generate_fn: Callable[[], None], progress_queue: Optional["queue.Queue[tuple[str,int,int]]"] = None):
            super().__init__()
            self.generate_fn = generate_fn
            self._error: Optional[str] = None
            self.allow_cancel = True
            self.progress_queue = progress_queue

        def compose(self) -> ComposeResult:
            yield Container(
                Header(show_clock=False),
                Static("WORLD GENERATION", id="title"),
                Static(self.status_text, id="status"),
                Static("", id="progress"),
                Static("", id="error"),
                Footer(),
                id="frame",
            )

        async def on_mount(self) -> None:
            if self.progress_queue:
                self.set_interval(0.1, self._drain_progress)
            asyncio.create_task(self._run_generation())

        def _drain_progress(self) -> None:
            if not self.progress_queue:
                return
            try:
                while True:
                    pref, idx, total = self.progress_queue.get_nowait()
                    self.total_pref = total
                    lines = list(self.progress_lines or [])
                    lines.append(f"{pref} ({idx}/{total})")
                    # Keep last 8 entries
                    self.progress_lines = lines[-8:]
                    self.query_one("#progress", Static).update("\n".join(self.progress_lines))
            except Exception:
                return

        async def _run_generation(self) -> None:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, self.generate_fn)
                self.success = True
            except Exception as exc:  # pragma: no cover - surface runtime errors
                self._error = str(exc)
                self.success = False
            finally:
                self.done = True
                if self._error:
                    self.query_one("#error", Static).update(f"Failed: {self._error}")
                    self.status_text = "Press Enter to exit"
                else:
                    self.status_text = "World generation complete! Press Enter to continue."
                self.query_one("#status", Static).update(self.status_text)

        def on_key(self, event) -> None:
            if not self.done:
                if event.key in {"escape", "q"} and self.allow_cancel:
                    self.done = True
                    self.success = False
                    self.exit(False)
                return
            if event.key:
                self.exit(self.success)


def run_tui_world_gen(generate_fn: Callable[[], None], *, progress_queue=None) -> Optional[bool]:
    """
    Run the world generation spinner overlay. Returns True/False on completion,
    or None if Textual is unavailable.
    """
    if not TUI_AVAILABLE:
        return None
    app = WorldGenApp(generate_fn, progress_queue=progress_queue)
    return app.run()
