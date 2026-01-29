"""
Textual-powered character creation driver.
Falls back to the existing console flow if Textual is unavailable.
"""
from __future__ import annotations

import asyncio
import os
import random
from typing import List, Optional, TYPE_CHECKING

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Vertical, Horizontal
    from textual.widgets import Button, Checkbox, DataTable, Footer, Header, Input, OptionList, Static
    from textual.reactive import reactive
    from textual.coordinate import Coordinate

    TUI_AVAILABLE = True
except Exception:
    TUI_AVAILABLE = False
    if TYPE_CHECKING:
        # Hint the type checker even if runtime imports fail.
        from textual.app import App, ComposeResult  # type: ignore
        from textual.containers import Container, Vertical, Horizontal  # type: ignore
        from textual.widgets import Button, Checkbox, DataTable, Footer, Header, Input, OptionList, Static  # type: ignore
        from textual.reactive import reactive  # type: ignore
        from textual.coordinate import Coordinate  # type: ignore
    else:
        class App:  # minimal stub to keep linting quiet
            def __init__(self, *_, **__):
                pass
            def exit(self, *_):
                pass

        class ComposeResult:
            pass

        class _WidgetStub:
            def __init__(self, *_, **__):
                pass

        Container = Vertical = Horizontal = Button = Checkbox = DataTable = Footer = Header = Input = OptionList = Static = _WidgetStub

        def reactive(*args, **kwargs):  # noqa: D401 - stub
            return None

        class Coordinate:
            def __init__(self, row: int = 0, column: int = 0) -> None:
                self.row = row
                self.column = column

from game.personnel.create_player import (
    CLEAR_SCREEN,
    MIN_PITCHES,
    MAX_PITCHES,
    CreatePlayerEngine,
)


def _strip_clear(lines: List[str]) -> List[str]:
    """Remove CLEAR_SCREEN markers and trailing empties."""
    buf: List[str] = []
    for line in lines:
        if not line or line == CLEAR_SCREEN:
            continue
        buf.append(line)
    return buf


if TUI_AVAILABLE:

    class _BasePromptApp(App[str]):
        CSS = """
        Screen {
            align: center middle;
            background: #0d1117;
        }
        #frame {
            width: 88;
            height: auto;
            border: round #58a6ff;
            padding: 1 2;
            background: #0b0f14;
        }
        #log {
            height: auto;
            color: #c9d1d9;
        }
        #prompt {
            color: #58a6ff;
            height: auto;
        }
        OptionList {
            width: 100%;
        }
        """

        def __init__(self, *, log_lines: List[str], prompt: str) -> None:
            super().__init__()
            self.log_lines = _strip_clear(log_lines)
            self.prompt_text = prompt
            self.result_value: Optional[str] = None

        def _finish(self, value: str) -> None:
            self.result_value = value
            self.exit(value)


    class _SelectApp(_BasePromptApp):
        def __init__(self, *, log_lines: List[str], prompt: str, options: List[str], default_idx: int = 0) -> None:
            super().__init__(log_lines=log_lines, prompt=prompt)
            self.options = options
            self.default_idx = max(0, min(default_idx, len(options) - 1))

        def compose(self) -> ComposeResult:
            opt_items = [f"{i+1}. {opt}" for i, opt in enumerate(self.options)]
            yield Container(
                Header(show_clock=False),
                Static("\n".join(self.log_lines), id="log"),
                Static(self.prompt_text, id="prompt"),
                OptionList(*opt_items, id="olist"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            opt = self.query_one(OptionList)
            opt.focus()
            if self.options:
                opt.highlighted = self.default_idx

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            idx = event.option_index
            self._finish(str(idx + 1))

        def action_quit(self) -> None:
            self._finish("__ESC__")


    class _MenuGridApp(_BasePromptApp):
        """Menu-style prompt that shows prefix/suffix blocks and supports a roulette animation hook."""

        CSS = _BasePromptApp.CSS + """
        #prefix, #suffix { color: #c9d1d9; width: 100%; min-height: 1; }
        #roulette { color: #58a6ff; height: 1; }
        DataTable {
            width: 100%;
            height: auto;
            border: solid #30363d;
        }
        """

        def __init__(
            self,
            *,
            log_lines: List[str],
            prompt: str,
            options: List[str],
            default_idx: int = 0,
            prefix: str = "",
            suffix: str = "",
            roulette: bool = False,
            cols: int = 3,
            col_width: int = 24,
        ) -> None:
            super().__init__(log_lines=log_lines, prompt=prompt)
            self.options = options
            self.default_idx = max(0, min(default_idx, len(options) - 1))
            self.prefix = prefix
            self.suffix = suffix
            self.roulette = roulette
            self._spinning = False
            self.cols = max(1, cols)
            self.col_width = max(12, col_width)

        def compose(self) -> ComposeResult:
            table = DataTable(
                show_header=False,
                show_row_labels=False,
                zebra_stripes=False,
                cursor_type="cell",
                id="grid",
            )
            for col in range(self.cols):
                table.add_column("", width=self.col_width, key=str(col))
            rows: List[List[str]] = []
            for i in range(0, len(self.options), self.cols):
                row = self.options[i : i + self.cols]
                while len(row) < self.cols:
                    row.append("")
                rows.append(row)
            for row in rows:
                table.add_row(*row)

            yield Container(
                Header(show_clock=False),
                Static(self.prefix, id="prefix", expand=True),
                table,
                Static(self.suffix, id="suffix", expand=True),
                Static("", id="roulette"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            table = self.query_one(DataTable)
            table.focus()
            if self.options:
                row = self.default_idx // self.cols
                col = self.default_idx % self.cols
                table.cursor_coordinate = Coordinate(row, col)

        def _finish_idx(self, idx: int) -> None:
            self._finish(str(idx + 1))

        async def _spin_and_finish(self, idx: int) -> None:
            """Lightweight roulette animation before finishing."""
            self._spinning = True
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            target = self.query_one("#roulette", Static)
            for i in range(14):
                target.update(f"Spinning... {frames[i % len(frames)]}")
                await asyncio.sleep(0.08)
            target.update("")
            self._spinning = False
            self._finish_idx(idx)

        def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
            row, col = event.coordinate
            idx = (row * self.cols) + col
            if idx >= len(self.options):
                return
            label = (self.options[idx] or "").lower()
            if self.roulette and "reroll" in label and not self._spinning:
                asyncio.create_task(self._spin_and_finish(idx))
                return
            self._finish_idx(idx)

        def action_quit(self) -> None:
            self._finish("__ESC__")


    class _InputApp(_BasePromptApp):
        CSS = _BasePromptApp.CSS + """
        Input {
            width: 100%;
        }
        """

        def compose(self) -> ComposeResult:
            yield Container(
                Header(show_clock=False),
                Static("\n".join(self.log_lines), id="log"),
                Static(self.prompt_text, id="prompt"),
                Input(placeholder="Type response (Esc to cancel)...", id="text"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            self.query_one(Input).focus()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            self._finish(event.value)

        def action_quit(self) -> None:
            self._finish("__ESC__")


    class _PitchSelectApp(_BasePromptApp):
        CSS = _BasePromptApp.CSS + """
        #choices {
            height: auto;
            gap: 1;
        }
        Horizontal {
            width: 100%;
            gap: 2;
        }
        Checkbox {
            width: 50%;
        }
        Button {
            margin-top: 1;
        }
        """

        error_text = reactive("")

        def __init__(self, *, log_lines: List[str], prompt: str, options: List[str], selected: List[str]) -> None:
            super().__init__(log_lines=log_lines, prompt=prompt)
            self.options = options
            self.selected = set(selected or [])

        def _update_count(self) -> None:
            count = sum(1 for cb in self.query(Checkbox) if cb.value)
            label = f"Selected {count}/{len(self.options)} (need {MIN_PITCHES}-{MAX_PITCHES})"
            self.query_one("#count", Static).update(label)

        def compose(self) -> ComposeResult:
            rows: List[Horizontal] = []
            for i in range(0, len(self.options), 2):
                row_checks = []
                for j in range(2):
                    idx = i + j
                    if idx < len(self.options):
                        opt = self.options[idx]
                        row_checks.append(Checkbox(f"{idx+1}. {opt}", value=(opt in self.selected)))
                rows.append(Horizontal(*row_checks))
            yield Container(
                Header(show_clock=False),
                Static("\n".join(self.log_lines), id="log"),
                Static(self.prompt_text, id="prompt"),
                Vertical(*rows, id="choices"),
                Static("", id="count"),
                Button("Confirm", id="confirm", variant="primary"),
                Button("Cancel", id="cancel"),
                Static("", id="error"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            first = self.query_one(Checkbox)
            first.focus()
            self._update_count()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "cancel":
                self._finish("__ESC__")
                return
            picks = [cb.label.split(". ", 1)[1] for cb in self.query(Checkbox) if cb.value]
            if len(picks) < MIN_PITCHES or len(picks) > MAX_PITCHES:
                err = f"Select {MIN_PITCHES}-{MAX_PITCHES} pitches. Current: {len(picks)}"
                self.query_one("#error", Static).update(err)
                return
            self._finish(",".join(picks))

        def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
            self._update_count()

        def action_quit(self) -> None:
            self._finish("__ESC__")


    class _StarterSpinApp(_BasePromptApp):
        CSS = _BasePromptApp.CSS + """
        Button {
            margin-top: 1;
        }
        """

        def __init__(self, *, log_lines: List[str], prompt: str, odds: float, label: str, header_text: str = "") -> None:
            super().__init__(log_lines=log_lines, prompt=prompt)
            self.odds = odds
            self.label = label
            self.header_text = header_text
            self._spinning = False

        def compose(self) -> ComposeResult:
            # Mirror the CLI: show the full banner + stat preview above the prompt.
            log_block = list(self.log_lines)
            if self.header_text:
                log_block.append(self.header_text)
            display_log = "\n".join(log_block)
            yield Container(
                Header(show_clock=False),
                Static(display_log, id="log"),
                Static(f"{self.prompt_text}\nPress Enter to spin for {self.label}; Esc to cancel.", id="prompt"),
                Button("Spin", id="spin", variant="primary"),
                Static("", id="result"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            self.query_one(Button).focus()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "spin":
                if not self._spinning:
                    asyncio.create_task(self._do_spin())
                return

        def action_quit(self) -> None:
            self._finish("__ESC__")

        async def _do_spin(self) -> None:
            self._spinning = True
            result = self.query_one("#result", Static)
            frames = ["🎲", "💫", "✨", "⭐", "💫", "🎲"]
            for i in range(14):
                result.update(f"Spinning... {frames[i % len(frames)]}")
                await asyncio.sleep(0.07)
            win = random.random() < self.odds
            msg = "WIN! Starter Trait unlocked." if win else "Missed. No Starter Trait (for now)."
            result.update(msg)
            self._spinning = False
            self._finish("WIN" if win else "LOSE")


def _prompt_tui(request, *, log_lines: List[str]) -> str:
    """Render a single prompt via Textual and return the response string."""
    if not TUI_AVAILABLE:
        raise RuntimeError("Textual unavailable")

    prompt_msg = request.message or ""
    options = request.options or []
    payload = request.payload or {}

    if request.input_mode == "pitch_grid":
        selected = list(payload.get("selected", []))
        app = _PitchSelectApp(
            log_lines=log_lines,
            prompt=prompt_msg or "Select pitches",
            options=options,
            selected=selected,
        )
        return app.run()

    if request.input_mode == "starter_spin":
        odds = float(payload.get("odds", 0.35))
        label = payload.get("label", "Starter Trait")
        header_raw = payload.get("header", "")
        header_lines: list[str] = []
        header_text = ""
        if isinstance(header_raw, list):
            header_lines = [str(line) for line in header_raw]
            header_text = "\n".join(header_lines)
        elif isinstance(header_raw, str):
            header_text = header_raw
        else:
            header_text = str(header_raw) if header_raw else ""
        combined_logs = log_lines + header_lines if header_lines else log_lines
        app = _StarterSpinApp(log_lines=combined_logs, prompt=prompt_msg or "Spin", odds=odds, label=label, header_text=header_text)
        return app.run()

    if request.input_mode == "menu_grid":
        prefix_raw = payload.get("prefix", "")
        if isinstance(prefix_raw, list):
            prefix = "\n".join(prefix_raw)
        else:
            prefix = prefix_raw or ""
        suffix_raw = payload.get("suffix", "")
        if isinstance(suffix_raw, list):
            suffix = "\n".join(suffix_raw)
        else:
            suffix = suffix_raw or ""
        if not isinstance(prefix, str):
            prefix = str(prefix)
        if not isinstance(suffix, str):
            suffix = str(suffix)
        default_idx = 0
        if str(request.default).isdigit():
            d = int(request.default)
            default_idx = max(0, min(len(options) - 1, d - 1))
        app = _MenuGridApp(
            log_lines=log_lines,
            prompt=prompt_msg,
            options=options,
            default_idx=default_idx,
            prefix=prefix,
            suffix=suffix,
            roulette=bool(payload.get("roulette")),
            cols=int(payload.get("cols", 3) or 3),
            col_width=int(payload.get("col_width", 24) or 24),
        )
        return app.run()

    if request.options:
        default_idx = 0
        if str(request.default).isdigit():
            d = int(request.default)
            default_idx = max(0, min(len(options) - 1, d - 1))
        app = _SelectApp(log_lines=log_lines, prompt=prompt_msg, options=options, default_idx=default_idx)
        return app.run()

    app = _InputApp(log_lines=log_lines, prompt=prompt_msg)
    return app.run()


def run_tui_create_player(session) -> Optional[int]:
    """
    Drive CreatePlayerEngine with a Textual UI.
    Returns created player id or None.
    """
    if not TUI_AVAILABLE:
        return None

    engine = CreatePlayerEngine(session)
    response: Optional[str] = None
    log_buffer: List[str] = []

    while True:
        result = engine.advance(response)
        response = None
        for request in result.requests:
            if request.kind == "log":
                if request.message == CLEAR_SCREEN:
                    log_buffer.clear()
                else:
                    log_buffer.append(request.message)
            elif request.kind == "prompt":
                response = _prompt_tui(request, log_lines=log_buffer)
        if result.done and engine.result() is not None:
            return engine.result()
        if engine.is_complete():
            return engine.result()
    return None
