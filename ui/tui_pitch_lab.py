"""
Textual UI for Pitch Lab: shows repertoire with mastery/progress and allows
signature unlocks and talent tree entry. Returns when user exits.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from game.mechanics.pitch_mastery import mastery_level_for_xp, MASTERY_THRESHOLDS

TUI_AVAILABLE = False

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal
    from textual.widgets import Header, Footer, OptionList, Static, Button
    from textual.reactive import reactive

    TUI_AVAILABLE = True
except Exception:
    TUI_AVAILABLE = False


def _progress_label(xp: int, level: int) -> tuple[str, str]:
    prev = MASTERY_THRESHOLDS[level - 1] if level > 0 else 0
    nxt = MASTERY_THRESHOLDS[level] if level < len(MASTERY_THRESHOLDS) else None
    if nxt is None:
        return "Mastered", ""
    span = max(1, nxt - prev)
    prog = max(0, xp - prev)
    return f"{prog}/{span}", f"{int((prog/span)*100)}%"


if TUI_AVAILABLE:

    class PitchLabApp(App[bool]):
        CSS = """
        Screen { align: center middle; background: #0d1117; }
        #frame { width: 100; height: 90%; border: round #58a6ff; padding: 1 2; background: #0b0f14; }
        #title { color: #58a6ff; text-style: bold; height: 2; }
        #subtitle { color: #8b949e; height: 1; }
        OptionList { width: 100%; }
        #status { color: #c9d1d9; }
        #error { color: tomato; }
        """

        status_text = reactive("")

        def __init__(self, *, ability_points: int, entries: Sequence[dict]):
            super().__init__()
            self.ability_points = ability_points
            self.entries = list(entries)
            self.choice: Optional[str] = None
            self.selected_idx: int = 0

        def compose(self) -> ComposeResult:
            yield Container(
                Header(show_clock=False),
                Static("PITCH LAB", id="title"),
                Static(f"Ability Points: {self.ability_points}", id="subtitle"),
                OptionList(*(self._format_entry(e) for e in self.entries), id="olist"),
                Horizontal(
                    Button("Unlock Signature", id="unlock", variant="primary"),
                    Button("Talent Tree", id="talent"),
                    Button("Exit", id="exit"),
                ),
                Static("", id="status"),
                Static("", id="error"),
                Footer(),
                id="frame",
            )

        def _format_entry(self, entry: dict) -> str:
            name = entry.get("pitch_name", "Pitch")
            level = entry.get("level", 0)
            prog = entry.get("progress", "")
            sig = entry.get("signature")
            sig_txt = ""
            if sig:
                sig_txt = f" | Sig: {sig}"
                if entry.get("sig_unlocked"):
                    sig_txt += " (Unlocked)"
                elif entry.get("sig_ready"):
                    sig_txt += " (Ready)"
            return f"{name} Lv{level} — {prog}{sig_txt}"

        def on_mount(self) -> None:
            olist = self.query_one(OptionList)
            olist.focus()

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            self.selected_idx = event.option_index

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "exit":
                self.exit(False)
                return
            if event.button.id == "talent":
                self.choice = "TALENT"
                self.exit(True)
                return
            if event.button.id == "unlock":
                self.choice = "UNLOCK"
                self.exit(True)
                return

        def action_quit(self) -> None:
            self.exit(False)


def run_tui_pitch_lab(repertoire: Sequence, ability_points: int) -> Optional[tuple[str, Optional[int]]]:
    """
    Render Pitch Lab in Textual.
    Returns (action, index) where action in {"UNLOCK","TALENT","EXIT"}; index is selected pitch (0-based) for unlock.
    None if unavailable or cancelled.
    """
    if not TUI_AVAILABLE:
        return None

    entries = []
    for pitch in repertoire:
        xp = int(getattr(pitch, "mastery_xp", 0) or 0)
        level = mastery_level_for_xp(xp)
        prog, _pct = _progress_label(xp, level)
        entries.append(
            {
                "pitch_name": getattr(pitch, "pitch_name", "Pitch"),
                "level": level,
                "progress": prog,
                "signature": getattr(pitch, "signature_tag", None),
                "sig_unlocked": bool(getattr(pitch, "signature_unlocked", False)),
                "sig_ready": bool(getattr(pitch, "signature_ready", False)),
            }
        )

    app = PitchLabApp(ability_points=ability_points, entries=entries)
    res = app.run()
    if res is None:
        return None

    action = app.choice or ("EXIT" if res is False else "EXIT")
    idx = getattr(app, "selected_idx", 0)
    return action, idx
