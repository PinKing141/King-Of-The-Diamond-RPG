from __future__ import annotations

import time
from typing import Any, List, Optional

from core.io_interface import IOInterface
from core.renderer import ConsoleRenderer
from debug.debug_tools import input_with_debug
from ui.ui_core import choose_theme, panel, DEFAULT_THEME, show_page
from ui.ui_display import Colour, clear_screen, render_screen, render_weekly_dashboard
from ui.core import MenuChoice, UI, ui as default_ui
from game.save_manager import show_save_menu
from game.interfaces import SeasonView
from world.ui.scouting_report import view_scouting_menu
from game.story.event_manager import EventRequest
from core.decisions import DecisionRequest


def _safe_input(prompt: str, default: str = "", ui: Optional[UI] = None) -> str:
    if ui is not None:
        return ui.prompt(prompt, default=default)
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return default


class ConsoleIO(IOInterface):
    """Console implementation of IOInterface used by logic modules."""

    def __init__(self, renderer: Optional[ConsoleRenderer] = None) -> None:
        self.renderer = renderer or ConsoleRenderer()

    def log(self, message: str, *, level: str = "info") -> None:
        if level == "story":
            print(self.renderer.colorize(f"[Story] {message}", style="story"))
            return
        style = level if level in {"error", "fail", "warning", "warn"} else "info"
        print(self.renderer.colorize(message, style=style))

    def prompt(self, prompt: str, *, options: Optional[List[str]] = None) -> str:
        while True:
            try:
                response = input(prompt)
            except (EOFError, KeyboardInterrupt):
                return ""
            if options is None or not options:
                return response
            if response in options:
                return response
            print(f"Please enter one of: {', '.join(options)}")

    def clear(self) -> None:
        clear_screen()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


def render_event_requests(requests: List[EventRequest], *, io: Optional[IOInterface] = None) -> None:
    """Render EventRequests through IO; fall back to console prints."""
    target_io = io or ConsoleIO()
    for req in requests:
        if req.kind == "log":
            target_io.log(req.message, level=req.level)
        elif req.kind == "prompt":
            target_io.prompt(req.message, options=req.options)
        else:
            target_io.log(req.message)


class ConsoleView(SeasonView):
    """Console implementation of the SeasonView contract."""

    def __init__(
        self,
        *,
        theme: str = DEFAULT_THEME,
        ui_layer: Optional[UI] = None,
        io: Optional[IOInterface] = None,
    ) -> None:
        self.theme = theme
        self.io = io or ConsoleIO()
        base_ui = ui_layer or default_ui
        self.ui = base_ui.with_io(self.io).with_theme(theme)

    # ---------- shared helpers ----------
    def show_banner(self) -> None:
        self.ui.clear()
        theme = choose_theme(self.theme)
        width = 68
        deco = theme["decor"] * width
        title = "⚾  KING OF THE DIAMOND RPG: THE FINAL  ⚾"
        subtitle = "The Road to the Sacred Stadium begins here."
        self.ui.log(f"{theme['accent']}{deco}{Colour.RESET}")
        self.ui.log(f"{theme['accent']}{title.center(width)}{Colour.RESET}")
        self.ui.log(f"{theme['accent']}{deco}{Colour.RESET}")
        self.ui.log(f"{theme['muted']}{subtitle.center(width)}{Colour.RESET}\n")

    def show_week_header(self, *, year: int, week: int, week_max: int, month: int) -> None:
        month_label = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        label = month_label[(month - 1) % 12] if month else "--"
        self.ui.log(f"{Colour.gold}>>> YEAR {year} | WEEK {week} / {week_max}{Colour.RESET}")
        self.ui.log(f"Date: {label} (Month {month})")

    def display_story_event(self, message: str) -> None:
        self.ui.log(f"{Colour.CYAN}[Story]{Colour.RESET} {message}")

    def display_info(self, message: str) -> None:
        self.ui.log(message)

    def display_warning(self, message: str) -> None:
        self.ui.log(f"{Colour.WARNING}{message}{Colour.RESET}", level="warning")

    def display_error(self, message: str) -> None:
        self.ui.log(f"{Colour.FAIL}{message}{Colour.RESET}", level="error")

    def display_rivalry_detected(self, school_name: str) -> None:
        self.ui.log(f"\n{Colour.RED}!!! RIVAL MATCH DETECTED !!!{Colour.RESET}")
        self.ui.log(f"You will face {school_name}. Your nemesis awaits.")
        self.ui.log(f"{Colour.YELLOW}Cue: Rival theme | Pre-game taunt unlocked{Colour.RESET}")

    def display_rivalry_aura(self) -> None:
        self.ui.log(f"{Colour.MAGENTA}Heads up:{Colour.RESET} Big game aura this week. No rival intel found, but the band is on standby.")

    def prompt_continue(self, prompt: str = "Press Enter to continue...") -> None:
        _safe_input(prompt, ui=self.ui)

    def prompt_yes_no(self, prompt: str) -> bool:
        return self.ui.confirm(prompt)

    # ---------- menus ----------
    def prompt_weekly_menu(self, *, scouting_available: bool, context: Any, session: Any, state: Any) -> str:
        while True:
            self.show_banner()
            self.show_week_header(
                year=getattr(state, "current_year", 0),
                week=getattr(state, "current_week", 0),
                week_max=50,
                month=getattr(state, "current_month", 0),
            )
            self.ui.log(f"{Colour.dim}Prepare your week:{Colour.RESET}\n")

            options = [
                MenuChoice("1", "Plan Week", value="PLAN_WEEK"),
                MenuChoice(
                    "2",
                    "Scouting Report",
                    value="SCOUT",
                    enabled=scouting_available,
                    hint="2",
                ),
                MenuChoice("3", "Character Sheet", value="CHARACTER_SHEET"),
                MenuChoice("4", "Save Game", value="SAVE"),
                MenuChoice("0", "Back to Main Menu", value="QUIT"),
            ]

            pre_choice = self.ui.menu(
                "Week Prep Options",
                options,
                prompt_text=">> ",
                clear_first=False,
                input_fn=lambda prompt: input_with_debug(prompt, context=context, session=session, state=state),
            )
            if pre_choice is None:
                continue
            if pre_choice == "SCOUT" and not scouting_available:
                self.ui.log("Scouting is only available when a match is scheduled this week.", level="warning")
                self.ui.wait(1)
                continue
            return pre_choice

    def prompt_command_menu(self, *, context: Any, session: Any, state: Any) -> str:
        while True:
            self.show_banner()
            self.show_week_header(
                year=getattr(state, "current_year", 0),
                week=getattr(state, "current_week", 0),
                week_max=50,
                month=getattr(state, "current_month", 0),
            )
            self.ui.log("\nOptions:")

            options = [
                MenuChoice("", "Next Week", value="NEXT_WEEK", hint="Enter"),
                MenuChoice("s", "Scouting / Roster", value="SCOUT"),
                MenuChoice("d", "Save Game", value="SAVE"),
                MenuChoice("a", "Smart Sim (Delegate Weeks)", value="SMART_SIM"),
                MenuChoice("q", "Quit to Menu", value="QUIT"),
            ]

            cmd = self.ui.menu(
                "Command Menu",
                options,
                prompt_text=">> ",
                clear_first=False,
                input_fn=lambda prompt: input_with_debug(prompt, context=context, session=session, state=state),
            )
            if cmd is None:
                continue
            return cmd

    def prompt_smart_sim(self, *, current_week: int, context: Any, session: Any, state: Any) -> Optional[int]:
        target_input = self.ui.prompt(
            f"Simulate until week (>{current_week}): ",
            input_fn=lambda prompt: input_with_debug(prompt, context=context, session=session, state=state),
        )
        target_input = target_input.strip()
        try:
            target_week = int(target_input) if target_input else current_week + 1
        except ValueError:
            self.ui.log("Invalid week.", level="warning")
            return None
        return target_week

    # ---------- screens ----------
    def show_character_sheet(self, session: Any, snapshot: dict) -> None:
        show_page(render_screen, session, snapshot)
        _safe_input("Press Enter to return...", ui=self.ui)

    def show_save_menu(self) -> None:
        show_page(show_save_menu, "SAVE")

    def show_scouting_menu(self, context: Any) -> None:
        show_page(view_scouting_menu, context)

    def show_weekly_dashboard(self, summary: Any) -> None:
        render_weekly_dashboard(summary)
        _safe_input("", ui=self.ui)

    def show_smart_sim_stop(self, reason: str) -> None:
        self.ui.log(f"\n{Colour.WARNING}Smart Sim stopped: {reason}{Colour.RESET}", level="warning")
        _safe_input("Press Enter to continue...", ui=self.ui)

    def show_progress(self, message: str, end: str = "\n") -> None:
        self.ui.stream(message, end=end)

    def show_fatal_error(self, title: str, body: str, details: Optional[str] = None) -> None:
        self.ui.clear()
        self.ui.log(f"\n{Colour.FAIL}{title}{Colour.RESET}", level="error")
        self.ui.log(body, level="error")
        if details:
            self.ui.log(details, level="error")
        self.prompt_continue()

    # ---------- main menu helpers ----------
    def prompt_main_menu(self, *, player_info: str, has_save: bool) -> str:
        self.show_banner()
        theme = choose_theme(self.theme)
        menu_lines = [
            f"{theme['muted']}Current Active Game: {Colour.CYAN}{player_info}{Colour.RESET}",
            "",
            f"{theme['accent']}[1]{Colour.RESET} Continue Active Game",
            f"{theme['accent']}[2]{Colour.RESET} Load Game (Select Slot)",
            f"{theme['accent']}[3]{Colour.RESET} New Career (Reuse Current World)",
            f"{theme['accent']}[4]{Colour.RESET} Rebuild World (Fresh Generation)",
            f"{theme['accent']}[5]{Colour.RESET} Exit",
        ]
        panel("Main Menu", menu_lines, theme=self.theme, width=70)
        return _safe_input("\nSelect: ", ui=self.ui).strip()

    def prompt_rebuild_world(self) -> bool:
        return self.prompt_yes_no(f"{Colour.RED}Rebuild entire world? This deletes all progress. (y/n): {Colour.RESET}")

    def prompt_new_career(self) -> bool:
        return self.prompt_yes_no("Create a new first-year in the existing world? (y/n): ")

    def announce_world_gen(self) -> None:
        self.ui.log(f"{Colour.WARNING}World not populated. Running World Generator...{Colour.RESET}", level="warning")

    def announce_world_gen_complete(self) -> None:
        self.ui.log(f"{Colour.GREEN}World Generation Complete.{Colour.RESET}")
        self.ui.wait(1)

    def announce_new_career_ready(self) -> None:
        self.ui.log(f"{Colour.GREEN}New career ready. Jumping into the season...{Colour.RESET}")

    # ---------- decision request bridge ----------
    def handle_decision_requests(self, requests: list) -> Optional[str]:
        """Bridge DecisionRequest flow back to existing console prompts."""

        for req in requests:
            if not isinstance(req, DecisionRequest):
                continue
            if req.kind == "prompt" and req.message == "weekly_menu":
                payload = req.payload or {}
                scouting_available = bool(payload.get("scouting_available"))
                return self.prompt_weekly_menu(
                    scouting_available=scouting_available,
                    context=payload.get("context"),
                    session=payload.get("session"),
                    state=payload.get("state"),
                )
            if req.kind == "prompt" and req.message == "command_menu":
                payload = req.payload or {}
                return self.prompt_command_menu(
                    context=payload.get("context"),
                    session=payload.get("session"),
                    state=payload.get("state"),
                )
        return None

    def announce_player_created(self) -> None:
        self.ui.log(f"{Colour.GREEN}Player Created. Welcome to High School Baseball.{Colour.RESET}")
        self.ui.wait(1)

    def announce_character_creation(self) -> None:
        self.ui.log(f"\n{Colour.CYAN}No player data found. Starting Character Creation...{Colour.RESET}")
        self.ui.wait(1)

    def info(self, message: str) -> None:
        self.ui.log(message)
