"""
Bridge the simulation backend to a lightweight Ursina UI.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ursina import Button, Entity, Text
from match_engine.controller import MatchController
from match_engine.pregame import prepare_match
from match_engine.scoreboard import Scoreboard
from match_engine.states import EventType
from database.setup_db import get_session
from player_roles.batter_controls import enable_gui_mode as enable_batter_gui
from player_roles.pitcher_controls import enable_gui_mode as enable_pitcher_gui


class GameRunner(Entity):
    def __init__(self) -> None:
        super().__init__()
        self.session = get_session()
        self.match_controller: Optional[MatchController] = None
        self.waiting_for_user = False
        self._bus = None

        self.status_text = Text(
            text="Welcome to King of the Diamond",
            position=(-0.8, 0.45),
            scale=1.5,
        )
        self.hint_text = Text(text="", position=(-0.8, 0.3), scale=1.0)
        self.action_menu = Entity(enabled=False)

    # --- Setup ---
    def start_match(self, home_id: int, away_id: int) -> None:
        state = prepare_match(home_id, away_id, self.session)
        state.gui_mode = True
        enable_batter_gui(True)
        enable_pitcher_gui(True)

        self.match_controller = MatchController(state, Scoreboard())
        self._wire_bus(getattr(self.match_controller, "bus", None))
        self.match_controller._start_match()
        self.status_text.text = "Match started. Waiting for prompt..."

    def _wire_bus(self, bus: Any) -> None:
        if not bus:
            return
        self._bus = bus
        bus.subscribe(EventType.BATTERS_EYE_PROMPT.value, self._on_batters_eye_prompt)

    # --- Event Handling ---
    def _on_batters_eye_prompt(self, payload: Dict[str, Any]) -> None:
        self.waiting_for_user = True
        self._show_choice_menu(payload)

    # --- UI ---
    def _clear_menu(self) -> None:
        for child in list(self.action_menu.children):
            child.disable()
            child.parent = None
        self.action_menu.enabled = False

    def _show_choice_menu(self, payload: Dict[str, Any]) -> None:
        self._clear_menu()
        options = payload.get("options", []) or []
        hint = payload.get("hint")
        if hint:
            self.hint_text.text = f"Hint: {hint}"
        else:
            self.hint_text.text = ""

        y = 0.1
        for opt in options:
            label = opt.get("label", opt.get("key", ""))
            key = opt.get("key")
            Button(
                parent=self.action_menu,
                text=label,
                position=(0, y),
                scale=(0.45, 0.1),
                on_click=lambda _=None, choice=key: self.submit_choice(choice),
            )
            y -= 0.14
        self.action_menu.enabled = True

    def submit_choice(self, choice_key: str) -> None:
        if not self.match_controller:
            return
        self.match_controller.simulation.submit_player_choice(choice_key)
        self.waiting_for_user = False
        self._clear_menu()
        self.status_text.text = "Choice locked. Continuing..."

    # --- Game Loop ---
    def update(self) -> None:
        if not self.match_controller or self.waiting_for_user:
            return
        outcome = self.match_controller.step()
        ctx = getattr(self.match_controller, "context", None)
        desc = getattr(getattr(ctx, "last_outcome", None), "description", None)
        if desc:
            self.status_text.text = desc

    def end(self) -> None:
        if self._bus:
            self._bus.clear()
        self._clear_menu()
        self.match_controller = None
        self.status_text.text = "Game ended."
