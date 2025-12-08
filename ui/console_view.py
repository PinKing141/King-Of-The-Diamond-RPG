from __future__ import annotations

import time
from typing import Any, List, Optional

from core.io_interface import IOInterface
from core.renderer import ConsoleRenderer
from debug.debug_tools import input_with_debug
from ui.ui_core import choose_theme, panel, DEFAULT_THEME, show_page
from ui.ui_display import Colour, clear_screen, render_screen, render_weekly_dashboard
from game.save_manager import show_save_menu
from game.interfaces import SeasonView
from world.ui.scouting_report import view_scouting_menu
from game.story.event_manager import EventRequest
from core.decisions import DecisionRequest


def _safe_input(prompt: str, default: str = "") -> str:
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

    def __init__(self, *, theme: str = DEFAULT_THEME) -> None:
        self.theme = theme

    # ---------- shared helpers ----------
    def show_banner(self) -> None:
        clear_screen()
        theme = choose_theme(self.theme)
        width = 68
        deco = theme["decor"] * width
        title = "⚾  KING OF THE DIAMOND RPG: THE FINAL  ⚾"
        subtitle = "The Road to the Sacred Stadium begins here."
        print(f"{theme['accent']}{deco}{Colour.RESET}")
        print(f"{theme['accent']}{title.center(width)}{Colour.RESET}")
        print(f"{theme['accent']}{deco}{Colour.RESET}")
        print(f"{theme['muted']}{subtitle.center(width)}{Colour.RESET}\n")

    def show_week_header(self, *, year: int, week: int, week_max: int, month: int) -> None:
        month_label = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        label = month_label[(month - 1) % 12] if month else "--"
        print(f"{Colour.gold}>>> YEAR {year} | WEEK {week} / {week_max}{Colour.RESET}")
        print(f"Date: {label} (Month {month})")

    def display_story_event(self, message: str) -> None:
        print(f"{Colour.CYAN}[Story]{Colour.RESET} {message}")

    def display_info(self, message: str) -> None:
        print(message)

    def display_warning(self, message: str) -> None:
        print(f"{Colour.WARNING}{message}{Colour.RESET}")

    def display_error(self, message: str) -> None:
        print(f"{Colour.FAIL}{message}{Colour.RESET}")

    def display_rivalry_detected(self, school_name: str) -> None:
        print(f"\n{Colour.RED}!!! RIVAL MATCH DETECTED !!!{Colour.RESET}")
        print(f"You will face {school_name}. Your nemesis awaits.")
        print(f"{Colour.YELLOW}Cue: Rival theme | Pre-game taunt unlocked{Colour.RESET}")

    def display_rivalry_aura(self) -> None:
        print(f"{Colour.MAGENTA}Heads up:{Colour.RESET} Big game aura this week. No rival intel found, but the band is on standby.")

    def prompt_continue(self, prompt: str = "Press Enter to continue...") -> None:
        _safe_input(prompt)

    def prompt_yes_no(self, prompt: str) -> bool:
        response = _safe_input(prompt)
        return response.strip().lower().startswith("y")

    # ---------- menus ----------
    def prompt_weekly_menu(self, *, scouting_available: bool, context: Any, session: Any, state: Any) -> str:
        while True:
            self.show_banner()
            self.show_week_header(year=getattr(state, "current_year", 0), week=getattr(state, "current_week", 0), week_max=50, month=getattr(state, "current_month", 0))
            print(f"{Colour.dim}Prepare your week:{Colour.RESET}")
            print("\nWeek Prep Options:")
            print(" 1. Plan Week")
            label = "2. Scouting Report" if scouting_available else "2. Scouting Report (locked — no game this week)"
            print(f" {label}")
            print(" 3. Character Sheet")
            print(" 4. Save Game")
            print(" 0. Back to Main Menu")

            pre_choice = input_with_debug(">> ", context=context, session=session, state=state)
            if pre_choice is None:
                continue
            pre_choice = pre_choice.strip().lower()

            if pre_choice == "1":
                return "PLAN_WEEK"
            if pre_choice == "2":
                if not scouting_available:
                    print("Scouting is only available when a match is scheduled this week.")
                    time.sleep(1)
                    continue
                return "SCOUT"
            if pre_choice == "3":
                return "CHARACTER_SHEET"
            if pre_choice == "4":
                return "SAVE"
            if pre_choice == "0":
                return "QUIT"
            print("Invalid choice.")

    def prompt_command_menu(self, *, context: Any, session: Any, state: Any) -> str:
        while True:
            self.show_banner()
            self.show_week_header(year=getattr(state, "current_year", 0), week=getattr(state, "current_week", 0), week_max=50, month=getattr(state, "current_month", 0))
            print("\nOptions:")
            print(" [Enter] Next Week")
            print(" [S] Scouting / Roster")
            print(" [D] Save Game")
            print(" [A] Smart Sim (Delegate Weeks)")
            print(" [Q] Quit to Menu")

            cmd_raw = input_with_debug(">> ", context=context, session=session, state=state)
            if cmd_raw is None:
                continue
            cmd = cmd_raw.strip().lower()

            if cmd == "s":
                return "SCOUT"
            if cmd == "d":
                return "SAVE"
            if cmd == "a":
                return "SMART_SIM"
            if cmd == "q":
                return "QUIT"
            if cmd == "":
                return "NEXT_WEEK"
            print("Invalid choice.")

    def prompt_smart_sim(self, *, current_week: int, context: Any, session: Any, state: Any) -> Optional[int]:
        target_input = input_with_debug(
            f"Simulate until week (>{current_week}): ",
            context=context,
            session=session,
            state=state,
        )
        if target_input is None:
            return None
        target_input = target_input.strip()
        try:
            target_week = int(target_input) if target_input else current_week + 1
        except ValueError:
            print("Invalid week.")
            return None
        return target_week

    # ---------- screens ----------
    def show_character_sheet(self, session: Any, snapshot: dict) -> None:
        show_page(render_screen, session, snapshot)
        _safe_input("Press Enter to return...")

    def show_save_menu(self) -> None:
        show_page(show_save_menu, "SAVE")

    def show_scouting_menu(self, context: Any) -> None:
        show_page(view_scouting_menu, context)

    def show_weekly_dashboard(self, summary: Any) -> None:
        render_weekly_dashboard(summary)
        _safe_input("")

    def show_smart_sim_stop(self, reason: str) -> None:
        print(f"\n{Colour.WARNING}Smart Sim stopped: {reason}{Colour.RESET}")
        _safe_input("Press Enter to continue...")

    def show_progress(self, message: str, end: str = "\n") -> None:
        print(message, end=end)

    def show_fatal_error(self, title: str, body: str, details: Optional[str] = None) -> None:
        clear_screen()
        print(f"\n{Colour.FAIL}{title}{Colour.RESET}")
        print(body)
        if details:
            print(details)
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
        return _safe_input("\nSelect: ").strip()

    def prompt_rebuild_world(self) -> bool:
        return self.prompt_yes_no(f"{Colour.RED}Rebuild entire world? This deletes all progress. (y/n): {Colour.RESET}")

    def prompt_new_career(self) -> bool:
        return self.prompt_yes_no("Create a new first-year in the existing world? (y/n): ")

    def announce_world_gen(self) -> None:
        print(f"{Colour.WARNING}World not populated. Running World Generator...{Colour.RESET}")

    def announce_world_gen_complete(self) -> None:
        print(f"{Colour.GREEN}World Generation Complete.{Colour.RESET}")
        time.sleep(1)

    def announce_new_career_ready(self) -> None:
        print(f"{Colour.GREEN}New career ready. Jumping into the season...{Colour.RESET}")

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
        time.sleep(1)

    def announce_player_created(self) -> None:
        print(f"{Colour.GREEN}Player Created. Welcome to High School Baseball.{Colour.RESET}")
        time.sleep(1)

    def announce_character_creation(self) -> None:
        print(f"\n{Colour.CYAN}No player data found. Starting Character Creation...{Colour.RESET}")
        time.sleep(1)

    def info(self, message: str) -> None:
        print(message)
