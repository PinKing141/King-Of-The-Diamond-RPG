"""
Textual weekly planner: choose actions per slot in a grid.
Returns (schedule_grid, skipped_mandatory) or (None, None) on cancel/unavailable.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

TUI_AVAILABLE = False

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal
    from textual.widgets import Header, Footer, OptionList, Static, Button
    from textual.reactive import reactive

    TUI_AVAILABLE = True
except Exception:
    TUI_AVAILABLE = False

try:
    from ui.tui_training_menu import run_tui_training_menu
except Exception:
    run_tui_training_menu = None  # type: ignore

DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
SLOTS = ("Morning", "Afternoon", "Evening")


def _format_slot_label(day_idx: int, slot_idx: int, action: Optional[str], mandatory: Optional[str]) -> str:
    base = f"{DAYS[day_idx]} {SLOTS[slot_idx]}"
    act = action.replace("_", " ").title() if action else ("Coach: " + mandatory.replace("_", " ").title() if mandatory else "Empty")
    if mandatory and action and action != mandatory:
        act += " (Overrides Coach)"
    if mandatory and not action:
        act = f"[Coach] {mandatory.replace('_', ' ').title()}"
    return f"{base}: {act}"


if TUI_AVAILABLE:

    class WeekPlannerApp(App[bool]):
        CSS = """
        Screen { align: center middle; background: #0d1117; }
        #frame { width: 100; height: 90%; border: round #58a6ff; padding: 1 2; background: #0b0f14; }
        #title { color: #58a6ff; text-style: bold; height: 2; }
        #subtitle { color: #8b949e; height: 1; }
        OptionList { width: 100%; height: 1fr; }
        #status { color: #c9d1d9; }
        #error { color: tomato; }
        """

        status_text = reactive("")

        def __init__(
            self,
            *,
            schedule_grid: List[List[Optional[str]]],
            mandatory_schedule: Dict[Tuple[int, int], str],
            coach_label: Optional[str],
        ):
            super().__init__()
            # Deep copy to avoid mutating caller if cancelled
            self.schedule = [[cell for cell in row] for row in schedule_grid]
            self.mandatory = dict(mandatory_schedule)
            self.coach_label = coach_label
            self.skipped: List[Dict[str, object]] = []
            self.selected_idx: int = 0

        def compose(self) -> ComposeResult:
            subtitle = self.coach_label or "Plan your week. Enter to edit slot. F = Finish, Esc/Q = Cancel"
            yield Container(
                Header(show_clock=False),
                Static("Weekly Planner", id="title"),
                Static(subtitle, id="subtitle"),
                OptionList(id="olist"),
                Horizontal(
                    Button("Finish", id="finish", variant="primary"),
                    Button("Cancel", id="cancel"),
                ),
                Static("", id="status"),
                Static("", id="error"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            self._render_list()

        def _render_list(self) -> None:
            olist = self.query_one(OptionList)
            olist.clear_options()
            for di in range(7):
                for si in range(3):
                    action = self.schedule[di][si]
                    mandatory = self.mandatory.get((di, si))
                    label = _format_slot_label(di, si, action, mandatory)
                    olist.add_option(label)
            olist.focus()
            olist.highlighted = min(self.selected_idx, len(olist.options) - 1)

        def _slot_from_index(self, idx: int) -> Tuple[int, int]:
            di = idx // 3
            si = idx % 3
            return di, si

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            self.selected_idx = event.option_index
            di, si = self._slot_from_index(self.selected_idx)
            mandatory = self.mandatory.get((di, si))
            label = f"Editing {DAYS[di]} {SLOTS[si]}"
            if mandatory:
                label += f" | Coach: {mandatory.replace('_', ' ').title()}"
            self._set_status(label)
            self._open_training_picker(di, si)

        def _open_training_picker(self, di: int, si: int) -> None:
            if run_tui_training_menu is None:
                return
            choice = run_tui_training_menu(day_label=DAYS[di], slot_label=SLOTS[si])
            if not choice:
                return
            if choice == "EXIT":
                return
            if choice == "BACK":
                self.schedule[di][si] = None
                self._render_list()
                return
            mandatory = self.mandatory.get((di, si))
            if mandatory == "b_team_match" and choice != mandatory:
                self._set_status("Coach assigned a B-Team scrimmage here.", error=True)
                return
            if mandatory and choice != mandatory:
                self.skipped.append({"day": di, "slot": si, "expected": mandatory})
            self.schedule[di][si] = choice
            self._render_list()

        def _set_status(self, text: str, *, error: bool = False) -> None:
            self.status_text = text
            self.query_one("#status", Static).update(text)
            self.query_one("#error", Static).update(text if error else "")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "cancel":
                self.exit(False)
            elif event.button.id == "finish":
                self.exit(True)

        def action_quit(self) -> None:
            self.exit(False)

        def action_f(self) -> None:
            self.exit(True)


def run_tui_week_planner(
    schedule_grid: List[List[Optional[str]]],
    mandatory_schedule: Dict[Tuple[int, int], str],
    *,
    coach_order=None,
    coach_order_requirement: Optional[str] = None,
) -> Optional[Tuple[List[List[Optional[str]]], List[Dict[str, object]]]]:
    if not TUI_AVAILABLE or run_tui_training_menu is None:
        return None

    coach_label = None
    if coach_order:
        req_text = coach_order_requirement or "Complete actions"
        coach_label = f"Coach's Order: {coach_order.description} ({req_text})"

    app = WeekPlannerApp(
        schedule_grid=schedule_grid,
        mandatory_schedule=mandatory_schedule,
        coach_label=coach_label,
    )
    res = app.run()
    if res is True:
        return app.schedule, app.skipped
    return None
