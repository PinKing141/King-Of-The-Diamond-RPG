import json
import random
import sys
import time
from typing import Optional, Tuple

from core.event_bus import EventBus
from database.setup_db import GameState, Player, School
from debug.debug_tools import input_with_debug
from core.analytics import initialise_analytics
from core.config_loader import SeasonConfigLoader
from core.exceptions import KoshienException, ScheduleError
from core.game_context import GameContext
from game.save_manager import show_save_menu
from game.loop.season_engine import run_end_of_season_logic
from game.loop.offseason_engine import graduate_third_years
from game.training_logic import run_training_camp_event
from game.loop.weekly_scheduler import build_mandatory_schedule, run_week_automatic, start_week
from ui.scouting_report import view_scouting_menu
from ui.ui_core import choose_theme, show_page, DEFAULT_THEME
from ui.ui_display import Colour, clear_screen, render_screen, render_weekly_dashboard
from world_sim.prefecture_engine import simulate_background_matches
from world_sim.qualifiers import run_season_qualifiers
from world_sim.tournament_sim import run_koshien_tournament, run_spring_koshien

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


class SeasonManager:
    """Orchestrates the weekly game loop, event triggers, and time advancement."""

    def __init__(self, context: GameContext, session, *, theme: str = DEFAULT_THEME):
        self.context = context
        self.session = session
        self.state: GameState = self._load_state()
        self.theme = theme
        self.bus = initialise_analytics(EventBus())

    # --------- helpers ---------
    def _load_state(self) -> GameState:
        return self.session.query(GameState).first()

    def _get_active_player(self) -> Optional[Player]:
        if not self.state or not self.state.active_player_id:
            return None
        return self.session.get(Player, self.state.active_player_id)

    def _has_game_this_week(self, player: Player, week: int) -> bool:
        if not player:
            return False

        try:
            mandatory = build_mandatory_schedule(player)
            if any("match" in (action or "") for action in mandatory.values()):
                return True
        except (AttributeError, ValueError) as exc:
            print(f"{Colour.WARNING}Warning: Could not check schedule: {exc}{Colour.RESET}")
            return False
        except Exception as exc:
            raise ScheduleError(f"Unexpected scheduler failure: {exc}") from exc

        return SeasonConfigLoader.is_tournament_week(week)

    def _run_story_arcs(self, user_player: Player) -> None:
        """Kick off or advance narrative arcs each week."""

        tracker = getattr(self.context, "story_tracker", None)
        if tracker is None:
            return

        last_week = self.context.get_temp_effect("story_arc_last_week")
        if last_week == self.state.current_week:
            return

        stats = {
            "recent_avg": getattr(user_player, "recent_avg", getattr(user_player, "batting_avg_recent", None)),
        }
        start_msg = tracker.check_triggers(user_player, stats)
        if start_msg:
            print(f"{Colour.CYAN}[Story]{Colour.RESET} {start_msg}")

        beats = tracker.advance_arcs(user_player)
        for _, beat in beats.items():
            print(f"{Colour.CYAN}[Story]{Colour.RESET} {beat}")

        self.context.set_temp_effect("story_arc_last_week", self.state.current_week)

    def _check_upcoming_rivalry(self, user_player: Player) -> None:
        """Scan the mandatory schedule for a rival matchup and warn the user."""

        if not user_player:
            return

        try:
            schedule = build_mandatory_schedule(user_player)
        except Exception as exc:
            print(f"{Colour.WARNING}Rivalry scan skipped: {exc}{Colour.RESET}")
            return

        match_event = None
        if isinstance(schedule, dict):
            # Some schedulers store match info as an entry value, not a named key.
            for val in schedule.values():
                if isinstance(val, dict) and val.get("match"):
                    match_event = val.get("match")
                    break
                if isinstance(val, str) and "match" in val:
                    match_event = val
                    break
        if not match_event:
            return

        opponent_school_id = None
        opponent_name = None
        if isinstance(match_event, dict):
            opponent_school_id = match_event.get("opponent_school_id") or match_event.get("school_id")
            opponent_name = match_event.get("opponent_name") or match_event.get("name")
        elif isinstance(match_event, str):
            label = match_event.lower()
            if "vs" in label:
                parts = match_event.split("vs", 1)
                opponent_name = parts[1].strip() if len(parts) > 1 else None
                if opponent_name:
                    opponent = (
                        self.session.query(School)
                        .filter(School.name.ilike(f"%{opponent_name}%"))
                        .first()
                    )
                    if opponent:
                        opponent_school_id = opponent.id

        rival_ctx = None
        if opponent_school_id:
            rival_ctx = self.context.get_rival_context(user_player.id, opponent_school_id)

        if not rival_ctx and opponent_school_id is None:
            print(f"{Colour.MAGENTA}Heads up:{Colour.RESET} Big game aura this week. No rival intel found, but the band is on standby.")
            return
        if not rival_ctx:
            return

        school = self.session.get(School, opponent_school_id) if opponent_school_id else None
        school_name = opponent_name or (getattr(school, "name", "Unknown School") if school else "Unknown School")

        print(f"\n{Colour.RED}!!! RIVAL MATCH DETECTED !!!{Colour.RESET}")
        print(f"You will face {school_name}. Your nemesis awaits.")
        print(f"{Colour.YELLOW}Cue: Rival theme | Pre-game taunt unlocked{Colour.RESET}")
        self.context.set_temp_effect("rival_match_context", rival_ctx)
        self.context.set_temp_effect("rival_presentation", {
            "music": "rival_theme",
            "dialogue_hook": "rival_pregame_taunt",
            "opponent_school": school_name,
        })

    def _print_week_header(self) -> None:
        month_label = MONTH_NAMES[(self.state.current_month - 1) % 12] if self.state.current_month else "--"
        print(f"{Colour.gold}>>> YEAR {self.state.current_year} | WEEK {self.state.current_week} / 50{Colour.RESET}")
        print(f"Date: {month_label} (Month {self.state.current_month})")

    def _print_banner(self) -> None:
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

    # --------- main loop ---------
    def run_season_loop(self) -> None:
        try:
            while True:
                self.state = self._load_state()
                user_player = self._get_active_player()
                if not user_player:
                    print(f"{Colour.FAIL}ERROR: Active player lost. Returning to menu.{Colour.RESET}")
                    break

                self.context.set_player(user_player.id, user_player.school_id)

                self._print_banner()
                self._print_week_header()
                self._run_story_arcs(user_player)
                self._check_upcoming_rivalry(user_player)

                if self.state.current_week > 50:
                    if self._handle_end_of_season(user_player):
                        break
                    self.session.expire_all()
                    self.state = self._load_state()
                    continue

                simulate_background_matches(user_player.school_id)
                self._handle_weekly_events(self.state.current_week, user_player.school_id)

                self.context.refresh_session()
                self.context.set_player(user_player.id, user_player.school_id)

                prep_action = self._run_weekly_menu(user_player)
                if prep_action == "QUIT":
                    break

                command = self._run_command_menu()
                if command == "QUIT":
                    break
                if command == "NEXT_WEEK":
                    self._advance_time()

        except KoshienException as exc:
            clear_screen()
            print(f"\n{Colour.FAIL}!!! GAME ERROR !!!{Colour.RESET}")
            print("A problem occurred that prevented the game from continuing:")
            print(f"{Colour.BOLD}{exc}{Colour.RESET}")
            print("\nProgress has been saved to 'crash_autosave.db' (if possible).")
            input("\nPress Enter to exit...")
            sys.exit(1)
        except Exception as exc:
            print(f"\n{Colour.FAIL}CRITICAL UNHANDLED EXCEPTION: {exc}{Colour.RESET}")
            raise
        finally:
            self.session.close()
            self.context.close_session()

    # --------- loop sections ---------
    def _handle_end_of_season(self, user_player: Player) -> bool:
        print(f"\n{Colour.HEADER}=== SEASON {self.state.current_year} COMPLETE ==={Colour.RESET}")

        if user_player.year == 3:
            print(f"\n{Colour.CYAN}CONGRATULATIONS ON YOUR GRADUATION!{Colour.RESET}")
            print("Thank you for playing Koshien RPG.")
            run_end_of_season_logic(user_player_id=self.context.player_id)
            input("Press Enter to exit...")
            return True

        print("The third-years are retiring. Preparing for next season...")
        input("[Press Enter to Advance Year]")

        run_end_of_season_logic()
        self.session.expire_all()
        return False

    def _handle_weekly_events(self, current_week: int, user_school_id: int) -> None:
        event_type = SeasonConfigLoader.get_event_for_week(current_week)
        if not event_type:
            return

        if event_type == "summer_qualifiers":
            print(f"\n{Colour.RED}!!! THE SUMMER KOSHIEN QUALIFIERS !!!{Colour.RESET}")
            input("Press Enter to begin...")
            reps = run_season_qualifiers(user_school_id, context=self.context)
            user_qualified = any(s.id == user_school_id for s in reps)
            if user_qualified:
                print(f"{Colour.gold}YOU WON THE PREFECTURE!{Colour.RESET}")
                run_koshien_tournament(user_school_id, reps, context=self.context)
            else:
                print(f"{Colour.FAIL}Eliminated in qualifiers.{Colour.RESET}")
                run_koshien_tournament(user_school_id, reps, context=self.context)

        elif event_type == "third_year_retirement":
            print(f"\n{Colour.WARNING}Third-years retire after summer. Time for the new team to step up.{Colour.RESET}")
            removed = graduate_third_years(self.session)
            try:
                self.session.commit()
            except Exception:
                self.session.rollback()
                removed = 0
            print(f"Removed {removed} graduating players. Set a new captain and lineup before autumn.")
            input("Press Enter to continue...")

        elif event_type == "autumn_regionals":
            from world_sim.regional_sim import run_autumn_regionals

            print(f"\n{Colour.gold}=== THE ROAD TO SENBATSU: AUTUMN REGIONALS ==={Colour.RESET}")
            print("The top schools from every prefecture clash for Spring bids.")
            input("Press Enter to begin...")

            qualifiers = run_autumn_regionals(self.session, user_school_id, context=self.context)
            self.context.set_temp_effect("spring_qualifier_ids", qualifiers)
            try:
                self.state.spring_qualifier_ids = json.dumps(qualifiers)
            except Exception:
                self.state.spring_qualifier_ids = None
            try:
                self.session.commit()
            except Exception:
                self.session.rollback()

            if user_school_id in qualifiers:
                print(f"\n{Colour.CYAN}Ticket punched! You qualified for Spring Koshien.{Colour.RESET}")
            else:
                print(f"\n{Colour.dim}You did not qualify for the Spring Tournament.{Colour.RESET}")

        elif event_type == "winter_camp":
            print(f"\n{Colour.WARNING}Winter Training Camp begins.{Colour.RESET}")
            if input("Participate? (y/n): ").lower() == "y":
                run_training_camp_event(self.context)
            else:
                print("You skipped camp.")

        elif event_type == "spring_koshien":
            print(f"\n{Colour.CYAN}Spring Senbatsu Approaches.{Colour.RESET}")
            qualifiers = self.context.get_temp_effect("spring_qualifier_ids") or getattr(self.state, "spring_qualifier_ids", None)
            if isinstance(qualifiers, str):
                try:
                    qualifiers = json.loads(qualifiers)
                except ValueError:
                    qualifiers = None
            run_spring_koshien(user_school_id, context=self.context, qualifiers=qualifiers)

    def _run_weekly_menu(self, user_player: Player) -> str:
        scouting_available = self._has_game_this_week(user_player, self.state.current_week)

        while True:
            self._print_banner()
            self._print_week_header()
            print(f"{Colour.dim}Prepare your week:{Colour.RESET}")
            print("\nWeek Prep Options:")
            print(" 1. Plan Week")
            label = "2. Scouting Report" if scouting_available else "2. Scouting Report (locked — no game this week)"
            print(f" {label}")
            print(" 3. Character Sheet")
            print(" 4. Save Game")
            print(" 0. Back to Main Menu")

            pre_choice = input_with_debug(">> ", context=self.context, session=self.session, state=self.state)
            if pre_choice is None:
                continue
            pre_choice = pre_choice.strip().lower()

            if pre_choice == "1":
                executed = show_page(start_week, self.context, self.state.current_week, self.state)
                if executed:
                    return "MENU"
                continue
            if pre_choice == "2":
                if not scouting_available:
                    print("Scouting is only available when a match is scheduled this week.")
                    time.sleep(1)
                    continue
                show_page(view_scouting_menu, self.context)
                continue
            if pre_choice == "3":
                show_page(render_screen, self.session, self._snapshot_player(user_player))
                input("Press Enter to return...")
                continue
            if pre_choice == "4":
                show_page(show_save_menu, "SAVE")
                continue
            if pre_choice == "0":
                return "QUIT"
            print("Invalid choice.")

    def _run_command_menu(self) -> str:
        while True:
            self._print_banner()
            self._print_week_header()
            print("\nOptions:")
            print(" [Enter] Next Week")
            print(" [S] Scouting / Roster")
            print(" [D] Save Game")
            print(" [A] Smart Sim (Delegate Weeks)")
            print(" [Q] Quit to Menu")

            cmd_raw = input_with_debug(">> ", context=self.context, session=self.session, state=self.state)
            if cmd_raw is None:
                continue
            cmd = cmd_raw.strip().lower()

            if cmd == "s":
                view_scouting_menu(self.context)
                continue
            if cmd == "d":
                show_save_menu("SAVE")
                continue
            if cmd == "a":
                self._prompt_smart_sim()
                self.session.refresh(self.state)
                continue
            if cmd == "q":
                return "QUIT"
            if cmd == "":
                return "NEXT_WEEK"
            print("Invalid choice.")

    # --------- smart sim ---------
    def _prompt_smart_sim(self) -> None:
        target_input = input_with_debug(
            f"Simulate until week (>{self.state.current_week}): ",
            context=self.context,
            session=self.session,
            state=self.state,
        )
        if target_input is None:
            return
        target_input = target_input.strip()
        try:
            target_week = int(target_input) if target_input else self.state.current_week + 1
        except ValueError:
            print("Invalid week.")
            return

        if target_week <= self.state.current_week:
            target_week = self.state.current_week + 1
        target_week = min(50, target_week)

        self._advance_time()
        if self.state.current_week >= target_week:
            return

        summaries, reason = self._run_smart_simulation(target_week)
        if summaries:
            render_weekly_dashboard(summaries[-1])
            input()
        if reason:
            print(f"\n{Colour.WARNING}Smart Sim stopped: {reason}{Colour.RESET}")
            input("Press Enter to continue...")
        self.session.refresh(self.state)

    def _run_smart_simulation(self, target_week: int) -> Tuple[list, Optional[str]]:
        summaries = []
        reason = None

        while self.state.current_week < target_week:
            player = self._get_active_player()
            if not player:
                reason = "No active player loaded."
                break

            reason = SeasonConfigLoader.get_interrupt_message(self.state.current_week)
            if reason:
                break

            if random.random() <= 0.40:
                reason = "Story event pending—take the reins."
                break

            user_school_id = player.school_id
            print(f"\r >> Processing Week {self.state.current_week}...", end="")
            simulate_background_matches(user_school_id, async_mode=True, verbose=True)

            self.context.refresh_session()
            self.context.set_player(player.id, user_school_id)
            _, summary = run_week_automatic(self.context, self.state.current_week)
            summaries.append(summary)
            if summary.stopped_by_interrupt:
                reason = summary.interrupt_reasons[-1] if summary.interrupt_reasons else "Week interrupted."
                break

            self._advance_time()

        print()
        return summaries, reason

    # --------- utilities ---------
    def _advance_time(self) -> None:
        self.state.current_week += 1
        if self.state.current_week % 4 == 0:
            self.state.current_month += 1
            if self.state.current_month > 12:
                self.state.current_month = 1
        self.session.commit()

    def _snapshot_player(self, player: Player) -> dict:
        school_name = getattr(player.school, "name", "Unknown") if getattr(player, "school", None) else "Unknown"
        return {
            "current_year": self.state.current_year,
            "current_month": self.state.current_month,
            "current_week": self.state.current_week,
            "last_name": getattr(player, "last_name", ""),
            "first_name": getattr(player, "first_name", ""),
            "position": getattr(player, "position", ""),
            "jersey_number": getattr(player, "jersey_number", 0),
            "school_name": school_name,
            "school_id": getattr(player, "school_id", None),
            "player_id": getattr(player, "id", None),
            "year": getattr(player, "year", 1),
            "control": getattr(player, "control", 0),
            "power": getattr(player, "power", 0),
            "velocity": getattr(player, "velocity", 0),
            "contact": getattr(player, "contact", 0),
            "stamina": getattr(player, "stamina", 0),
            "running": getattr(player, "running", 0),
            "breaking_ball": getattr(player, "breaking_ball", 0),
            "fielding": getattr(player, "fielding", 0),
            "fatigue": getattr(player, "fatigue", 0),
            "morale": getattr(player, "morale", 50),
        }
