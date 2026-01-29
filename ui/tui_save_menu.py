"""
Textual save/load selector with slot previews and confirmation.
Falls back to console menu if Textual is unavailable.
"""
from __future__ import annotations

import os
from typing import Optional

from game.save_manager import (
    get_save_slots,
    save_game,
    load_game,
    delete_autosave,
    SaveError,
    SaveCorruptError,
    SaveNotFoundError,
)

TUI_AVAILABLE = False

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, OptionList, Static
    from textual.containers import Container
    from textual.reactive import reactive

    TUI_AVAILABLE = True
except Exception:
    TUI_AVAILABLE = False


if TUI_AVAILABLE:

    class SaveMenuApp(App[bool]):
        CSS = """
        Screen {
            align: center middle;
            background: #0d1117;
        }
        #frame {
            width: 90;
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
        OptionList {
            width: 100%;
        }
        """

        status_text = reactive("Use arrows + Enter. Esc = back.")
        mode = reactive("SAVE")
        confirming = reactive(False)

        def __init__(self, mode: str = "SAVE"):
            super().__init__()
            self.mode = mode
            self._options: list[dict] = []
            self._confirm_payload: Optional[dict] = None

        def compose(self) -> ComposeResult:
            yield Container(
                Header(show_clock=False),
                Static(f"{self.mode} GAME", id="title"),
                Static(self.status_text, id="status"),
                OptionList(id="olist"),
                Static("", id="error"),
                Footer(),
                id="frame",
            )

        def on_mount(self) -> None:
            self._load_slots()
            self._render_options()

        def _load_slots(self) -> None:
            slots = get_save_slots()
            existing = {s["slot"]: s for s in slots}
            options: list[dict] = []
            for i in range(1, 6):
                if i in existing:
                    info = existing[i]
                    preview = info.get("preview") or ""
                    options.append(
                        {
                            "kind": "slot",
                            "slot": i,
                            "label": f"Slot {i} [{info['date']}]",
                            "details": preview,
                            "exists": True,
                        }
                    )
                else:
                    options.append({"kind": "slot", "slot": i, "label": f"Slot {i} [Empty]", "details": "", "exists": False})
            options.append({"kind": "autosave", "label": "Clear Autosave", "details": "", "exists": False})
            options.append({"kind": "back", "label": "Back", "details": "", "exists": False})
            self._options = options

        def _render_options(self, confirm: bool = False, prompt: str = "") -> None:
            olist = self.query_one(OptionList)
            olist.clear_options()
            if confirm and self._confirm_payload:
                olist.add_option(f"Yes — {prompt}")
                olist.add_option("No / Cancel")
                self.confirming = True
                olist.focus()
                return

            for opt in self._options:
                label = opt["label"]
                if opt.get("details"):
                    label = f"{label} · {opt['details']}"
                olist.add_option(label)
            self.confirming = False
            olist.focus()

        def _set_status(self, text: str, *, error: bool = False) -> None:
            self.status_text = text
            self.query_one("#status", Static).update(text)
            self.query_one("#error", Static).update(text if error else "")

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            if self.confirming:
                self._handle_confirm(event.option_index)
                return
            idx = event.option_index
            if idx < 0 or idx >= len(self._options):
                return
            choice = self._options[idx]
            kind = choice.get("kind")
            if kind == "back":
                self.exit(False)
                return
            if kind == "autosave":
                cleared = delete_autosave()
                self._set_status("Autosave cleared." if cleared else "No autosave found.")
                return
            if kind == "slot":
                self._handle_slot(choice)

        def _handle_slot(self, choice: dict) -> None:
            slot = choice["slot"]
            exists = choice.get("exists", False)
            if self.mode.upper() == "SAVE" and exists:
                self._confirm_payload = {"action": "save", "slot": slot}
                self._render_options(confirm=True, prompt=f"Overwrite Slot {slot}?")
                return
            if self.mode.upper() == "LOAD":
                if not exists:
                    self._set_status("Slot is empty.", error=True)
                    return
                self._confirm_payload = {"action": "load", "slot": slot}
                self._render_options(confirm=True, prompt=f"Load Slot {slot}? Unsaved progress will be lost.")
                return
            # Save new slot directly
            self._execute_action("save", slot)

        def _handle_confirm(self, idx: int) -> None:
            if idx != 0 or not self._confirm_payload:
                # Cancel
                self._confirm_payload = None
                self._render_options()
                return
            action = self._confirm_payload.get("action")
            slot = self._confirm_payload.get("slot")
            self._confirm_payload = None
            self._execute_action(action, slot)

        def _execute_action(self, action: str, slot: int) -> None:
            try:
                if action == "save":
                    _, msg = save_game(slot)
                    self._set_status(msg)
                    self.exit(True)
                    return
                if action == "load":
                    ok, msg = load_game(slot)
                    self._set_status(msg, error=not ok)
                    if ok:
                        self.exit(True)
                    return
            except SaveCorruptError as exc:
                self._set_status(f"CORRUPT: {exc}", error=True)
            except SaveNotFoundError as exc:
                self._set_status(str(exc), error=True)
            except SaveError as exc:
                self._set_status(f"Error: {exc}", error=True)
            self._render_options()

        def action_quit(self) -> None:
            self.exit(False)


def run_tui_save_menu(mode: str = "SAVE") -> Optional[bool]:
    """Launch the Textual save/load selector. Returns True on success, False on cancel, None if unavailable."""
    if not TUI_AVAILABLE:
        return None
    app = SaveMenuApp(mode=mode)
    return app.run()
