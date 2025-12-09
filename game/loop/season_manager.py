import json
import random
import sys
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError

from core.decisions import DecisionRequest, DecisionResult
from core.event_bus import EventBus
from database.setup_db import GameState, Player, School
from core.analytics import initialise_analytics
from core.config_loader import SeasonConfigLoader
from core.exceptions import KoshienException, ScheduleError
from core.game_context import GameContext
from core.services import SessionProvider
from game.loop.season_engine import SeasonEndResult, run_end_of_season_logic
from game.loop.offseason_engine import graduate_third_years
from game.training_logic import run_training_camp_event
from game.loop.weekly_scheduler import build_mandatory_schedule, run_week_automatic, start_week
from game.interfaces import SeasonView
from ui.ui_core import show_page
from world_sim.prefecture_engine import simulate_background_matches
from world_sim.qualifiers import run_season_qualifiers
from world_sim.tournament_sim import run_koshien_tournament, run_spring_koshien

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


class SeasonManager:
    """Orchestrates the weekly game loop, event triggers, and time advancement."""

    def __init__(
        self,
        context: GameContext,
        session,
        *,
        view: SeasonView,
        session_provider: SessionProvider | None = None,
    ):
        self.context = context
        self.session = session
        self.session_provider = session_provider
        self.state: GameState = self._load_state()
        self.view = view
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
            if any("match" in (action or "") for action in mandatory.values()):
            if any("match" in (action or "") for action in mandatory.values()):
                return True
        except (AttributeError, ValueError) as exc:
            self.view.display_warning(f"Warning: Could not check schedule: {exc}")
            return False
        except Exception as exc:
            raise ScheduleError(f"Unexpected scheduler failure: {exc}") from exc


    def _deliver_decision_requests(self, decision: DecisionResult, *, scouting_available: bool = False) -> Optional[str]:
        """Pass DecisionRequests to the view if supported, otherwise fall back to legacy prompts."""

        handler = getattr(self.view, "handle_decision_requests", None)
        if callable(handler):
            response = handler(decision.requests)
            if response is not None:
                return response

        for req in decision.requests:
            if req.kind != "prompt":
                continue
            if req.message == "weekly_menu":
                return self.view.prompt_weekly_menu(
                    scouting_available=scouting_available,
                    context=self.context,
                    session=self.session,
                    state=self.state,
                )
            if req.message == "command_menu":
                return self.view.prompt_command_menu(
                    context=self.context,
                    session=self.session,
                    state=self.state,
                )
        return None
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
            self.view.display_story_event(start_msg)

        beats = tracker.advance_arcs(user_player)
        for _, beat in beats.items():
            self.view.display_story_event(beat)

        self.context.set_temp_effect("story_arc_last_week", self.state.current_week)

    def _check_upcoming_rivalry(self, user_player: Player) -> None:
        """Scan the mandatory schedule for a rival matchup and warn the user."""

        if not user_player:
            return

        try:
            schedule = build_mandatory_schedule(user_player)
        except ScheduleError as exc:
            self.view.display_warning(f"Rivalry scan skipped: {exc}")
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
            self.view.display_rivalry_aura()
            return
        if not rival_ctx:
            return

        school = self.session.get(School, opponent_school_id) if opponent_school_id else None
        school_name = opponent_name or (getattr(school, "name", "Unknown School") if school else "Unknown School")

        self.view.display_rivalry_detected(school_name)
        self.context.set_temp_effect("rival_match_context", rival_ctx)
        self.context.set_temp_effect("rival_presentation", {
            "music": "rival_theme",
            "dialogue_hook": "rival_pregame_taunt",
            "opponent_school": school_name,
        })

    def _print_week_header(self) -> None:
        self.view.show_week_header(
            year=self.state.current_year,
            week=self.state.current_week,
            week_max=50,
            month=self.state.current_month,
        )

    def _print_banner(self) -> None:
        self.view.show_banner()

    def _render_events(self, events: List[Dict[str, Any]]) -> None:
        for event in events:
            payload = event.get("payload", {}) if isinstance(event, dict) else {}
            event_type = event.get("type") if isinstance(event, dict) else None

            if event_type == "SEASON_LOG":
                text = str(payload.get("text", ""))
                level = payload.get("level", "info")
                if level == "warning":
                    self.view.display_warning(text)
                elif level == "error":
                    self.view.display_error(text)
                else:
                    self.view.display_info(text)
                continue

            if event_type == "SEASON_EPILOGUE":
                title = payload.get("title", "EPILOGUE")
                desc = payload.get("description", "")
                story_lines = payload.get("story_lines", [])
                self.view.display_info(f"{title}: {desc}")
                for line in story_lines:
                    self.view.display_info(str(line))
                continue

            # Fallback for unrecognised events; keep visible in UI for debugging.
            self.view.display_info(str(payload) if payload else str(event))

    # --------- main loop ---------
    def run_season_loop(self) -> None:
        try:
            while True:
                self.state = self._load_state()
                user_player = self._get_active_player()
                if not user_player:
                    self.view.display_error("ERROR: Active player lost. Returning to menu.")
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

                simulate_background_matches(self.session, user_player.school_id, log=None)
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
            self.view.show_fatal_error(
                "!!! GAME ERROR !!!",
                "A problem occurred that prevented the game from continuing:",
                details=str(exc),
            )
            sys.exit(1)
        except Exception as exc:
            self.view.display_error(f"CRITICAL UNHANDLED EXCEPTION: {exc}")
            raise
        finally:
            self.session.close()
            self.context.close_session()

    # --------- loop sections ---------
    def _handle_end_of_season(self, user_player: Player) -> bool:
        self.view.display_info(f"=== SEASON {self.state.current_year} COMPLETE ===")

        if user_player.year == 3:
            self.view.display_info("CONGRATULATIONS ON YOUR GRADUATION!")
            self.view.display_info("Thank you for playing Koshien RPG.")
            result: SeasonEndResult = run_end_of_season_logic(
                self.session,
                user_player_id=self.context.player_id,
                event_bus=self.bus,
            )
            self._render_events(result.events)
            self.view.prompt_continue("Press Enter to exit...")
            return bool(result)

        self.view.display_info("The third-years are retiring. Preparing for next season...")
        self.view.prompt_continue("[Press Enter to Advance Year]")

        result: SeasonEndResult = run_end_of_season_logic(self.session, event_bus=self.bus)
        self._render_events(result.events)
        self.session.expire_all()
        return bool(result)

    def _handle_weekly_events(self, current_week: int, user_school_id: int) -> None:
        event_type = SeasonConfigLoader.get_event_for_week(current_week)
        if not event_type:
            return

        if event_type == "summer_qualifiers":
            self.view.display_info("!!! THE SUMMER KOSHIEN QUALIFIERS !!!")
            self.view.prompt_continue("Press Enter to begin...")
            reps = run_season_qualifiers(user_school_id, context=self.context)
            user_qualified = any(s.id == user_school_id for s in reps)
            if user_qualified:
                self.view.display_info("YOU WON THE PREFECTURE!")
                run_koshien_tournament(user_school_id, reps, context=self.context)
            else:
                self.view.display_warning("Eliminated in qualifiers.")
                run_koshien_tournament(user_school_id, reps, context=self.context)

        elif event_type == "third_year_retirement":
            self.view.display_warning("Third-years retire after summer. Time for the new team to step up.")
            removed = graduate_third_years(self.session)
            try:
                self.session.commit()
            except SQLAlchemyError as exc:
                self.session.rollback()
                self.view.display_error(f"Failed to persist retirements: {exc}")
                removed = 0
            self.view.display_info(f"Removed {removed} graduating players. Set a new captain and lineup before autumn.")
            self.view.prompt_continue("Press Enter to continue...")

        elif event_type == "autumn_regionals":
            from world_sim.regional_sim import run_autumn_regionals

            self.view.display_info("=== THE ROAD TO SENBATSU: AUTUMN REGIONALS ===")
            self.view.display_info("The top schools from every prefecture clash for Spring bids.")
            self.view.prompt_continue("Press Enter to begin...")

            qualifiers = run_autumn_regionals(self.session, user_school_id, context=self.context)
            self.context.set_temp_effect("spring_qualifier_ids", qualifiers)
            try:
                self.state.spring_qualifier_ids = json.dumps(qualifiers)
            except (TypeError, ValueError) as exc:
                self.state.spring_qualifier_ids = None
                self.view.display_warning(f"Could not persist qualifier ids: {exc}")
            try:
                self.session.commit()
            except SQLAlchemyError as exc:
                self.session.rollback()
                self.view.display_error(f"Failed to save autumn qualifiers: {exc}")

            if user_school_id in qualifiers:
                self.view.display_info("Ticket punched! You qualified for Spring Koshien.")
            else:
                self.view.display_info("You did not qualify for the Spring Tournament.")

        elif event_type == "winter_camp":
            self.view.display_warning("Winter Training Camp begins.")
            if self.view.prompt_yes_no("Participate? (y/n): "):
                run_training_camp_event(self.context)
            else:
                self.view.display_info("You skipped camp.")

        elif event_type == "spring_koshien":
            self.view.display_info("Spring Senbatsu Approaches.")
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
            decision = self._build_weekly_menu_decision(scouting_available=scouting_available)
            intent = self._deliver_decision_requests(decision, scouting_available=scouting_available)

            if intent == "PLAN_WEEK":
                executed = show_page(start_week, self.context, self.state.current_week, self.state)
                if executed:
                    return "MENU"
                continue
            if intent == "SCOUT":
                self.view.show_scouting_menu(self.context)
                continue
            if intent == "CHARACTER_SHEET":
                self.view.show_character_sheet(self.session, self._snapshot_player(user_player))
                continue
            if intent == "SAVE":
                self.view.show_save_menu()
                continue
            if intent == "QUIT":
                return "QUIT"

    def _run_command_menu(self) -> str:
        while True:
            decision = self._build_command_menu_decision()
            intent = self._deliver_decision_requests(decision)

            if intent == "SCOUT":
                self.view.show_scouting_menu(self.context)
                continue
            if intent == "SAVE":
                self.view.show_save_menu()
                continue
            if intent == "SMART_SIM":
                self._prompt_smart_sim()
                self.session.refresh(self.state)
                continue
            if intent == "QUIT":
                return "QUIT"
            if intent == "NEXT_WEEK":
                return "NEXT_WEEK"

    def _build_weekly_menu_decision(self, *, scouting_available: bool) -> DecisionResult:
        options = ["PLAN_WEEK", "SCOUT", "CHARACTER_SHEET", "SAVE", "QUIT"]
        req = DecisionRequest(
            kind="prompt",
            message="weekly_menu",
            options=options,
            payload={
                "scouting_available": scouting_available,
                "week": self.state.current_week,
                "context": self.context,
                "session": self.session,
                "state": self.state,
            },
        )
        return DecisionResult(summary=None, requests=[req], done=False)

    def _build_command_menu_decision(self) -> DecisionResult:
        options = ["SCOUT", "SAVE", "SMART_SIM", "QUIT", "NEXT_WEEK"]
        req = DecisionRequest(
            kind="prompt",
            message="command_menu",
            options=options,
            payload={
                "week": self.state.current_week,
                "context": self.context,
                "session": self.session,
                "state": self.state,
            },
        )
        return DecisionResult(summary=None, requests=[req], done=False)

    # --------- smart sim ---------
    def _prompt_smart_sim(self) -> None:
        target_week = self.view.prompt_smart_sim(
            current_week=self.state.current_week,
            context=self.context,
            session=self.session,
            state=self.state,
        )
        if target_week is None:
            return

        if target_week <= self.state.current_week:
            target_week = self.state.current_week + 1
        target_week = min(50, target_week)

        self._advance_time()
        if self.state.current_week >= target_week:
            return

        summaries, reason = self._run_smart_simulation(target_week)
        if summaries:
            self.view.show_weekly_dashboard(summaries[-1])
        if reason:
            self.view.show_smart_sim_stop(reason)
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
            self.view.show_progress(f"\r >> Processing Week {self.state.current_week}...", end="")
            simulate_background_matches(
                self.session,
                user_school_id,
                background=True,
                verbose=True,
                log=lambda msg: self.view.show_progress(msg) if hasattr(self.view, "show_progress") else None,
            )

            self.context.refresh_session()
            self.context.set_player(player.id, user_school_id)
            _, summary = run_week_automatic(self.context, self.state.current_week)
            summaries.append(summary)
            if summary.stopped_by_interrupt:
                reason = summary.interrupt_reasons[-1] if summary.interrupt_reasons else "Week interrupted."
                break

            self._advance_time()

        self.view.show_progress("")
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
