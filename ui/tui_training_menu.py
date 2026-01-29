"""
Textual picker for weekly training slot actions.
Returns the action token expected by plan_week_ui/get_slot_choice.
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

ACTION_OPTIONS = [
    ("Training: Power", "train_power"),
    ("Training: Speed", "train_speed"),
    ("Training: Stamina", "train_stamina"),
    ("Training: Control", "train_control"),
    ("Training: Contact", "train_contact"),
    ("Training: Bullpen Session", "bullpen_session"),
    ("Rest / Recovery", "rest"),
    ("Mindset: Study", "study"),
    ("Mindset: Friends", "social"),
    ("Mindset: Mind/Focus", "mind"),
    ("Role Request: Pitcher", "position_request_pitcher"),
    ("Role Request: Catcher", "position_request_catcher"),
    ("Role Request: Middle Infield", "position_request_middle_infield"),
    ("Role Request: Outfield", "position_request_outfield"),
    ("Back (undo)", "BACK"),
    ("Exit planning", "EXIT"),
]

if TUI_AVAILABLE:

    class TrainingMenuApp(App[str]):
        CSS = """
        Screen {
            align: center middle;
            background: #0d1117;
        }
        #frame {
            width: 80;
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

        def __init__(self, *, day_label: str, slot_label: str):
            super().__init__()
            self.day_label = day_label
            self.slot_label = slot_label
            self.choice: Optional[str] = None

        def compose(self) -> ComposeResult:
            subtitle = f"{self.day_label} — {self.slot_label}"
            yield Container(
                Header(show_clock=False),
                Static("Training Slot", id="title"),
                Static(subtitle, id="subtitle"),
                OptionList(*(label for label, _ in ACTION_OPTIONS), id="olist"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            self.query_one(OptionList).focus()

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            idx = event.option_index
            if 0 <= idx < len(ACTION_OPTIONS):
                self.choice = ACTION_OPTIONS[idx][1]
                self.exit(self.choice)

        def action_quit(self) -> None:
            self.choice = "EXIT"
            self.exit(self.choice)


def run_tui_training_menu(day_label: str = "", slot_label: str = "") -> Optional[str]:
    if not TUI_AVAILABLE:
        return None
    app = TrainingMenuApp(day_label=day_label, slot_label=slot_label)
    return app.run()
