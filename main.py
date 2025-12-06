import json
import sys
import os
import time
import random

from core.event_bus import EventBus
from database.setup_db import create_database, GameState, School, Player, get_session, safe_delete_db
from ui.ui_display import Colour, clear_screen, render_weekly_dashboard
from ui.ui_core import choose_theme, panel, DEFAULT_THEME
from game.weekly_scheduler import start_week, run_week_automatic
from world_sim.tournament_sim import run_koshien_tournament, run_spring_koshien
from world_sim.qualifiers import run_season_qualifiers
from world_sim.prefecture_engine import simulate_background_matches
from game.create_player import create_hero 
from game.season_engine import run_end_of_season_logic
from game.training_logic import run_training_camp_event
from game.save_manager import show_save_menu 
from game.game_context import GameContext
from game.analytics import initialise_analytics
from match_engine.controller import MatchController
from match_engine.commentary import CommentaryListener
from config import DATA_FOLDER

# Ensure database tables exist
create_database()

# Event bus + analytics initialisation
GLOBAL_EVENT_BUS = initialise_analytics(EventBus())

# -----------------------------------------------------
# UI
# -----------------------------------------------------

MAIN_MENU_THEME = DEFAULT_THEME


def print_banner(theme_name: str = MAIN_MENU_THEME):
    """Render the global banner with themed framing."""

    clear_screen()
    theme = choose_theme(theme_name)
    width = 68
    deco = theme["decor"] * width
    title = "⚾  KING OF THE DIAMOND RPG: THE FINAL  ⚾"
    subtitle = "The Road to the Sacred Stadium begins here."

    print(f"{theme['accent']}{deco}{Colour.RESET}")
    print(f"{theme['accent']}{title.center(width)}{Colour.RESET}")
    print(f"{theme['accent']}{deco}{Colour.RESET}")
    print(f"{theme['muted']}{subtitle.center(width)}{Colour.RESET}\n")


# -----------------------------------------------------
# FIRST TIME SETUP
# -----------------------------------------------------

def ensure_world_population(session):
    """Ensure the database has a populated world map."""
    try:
        school_count = session.query(School).count()
    except Exception:
        school_count = 0

    if school_count < 10:
        print(f"{Colour.WARNING}World not populated. Running World Generator...{Colour.RESET}")
        from database.populate_japan import populate_world

        populate_world()
        print(f"{Colour.GREEN}World Generation Complete.{Colour.RESET}")
        time.sleep(1)


def check_first_time_setup(session, state):
    """Populate world and ensure an active player exists."""

    ensure_world_population(session)

    # 2. Player creation
    player = load_active_player(session, state)
    if player:
        return player

    print(f"\n{Colour.CYAN}No player data found. Starting Character Creation...{Colour.RESET}")
    time.sleep(1)
    new_id = create_hero(session)
    if not new_id:
        return None

    state.active_player_id = new_id
    session.commit()

    print(f"{Colour.GREEN}Player Created. Welcome to High School Baseball.{Colour.RESET}")
    time.sleep(1)

    return session.get(Player, new_id)


# -----------------------------------------------------
# GAME STATE
# -----------------------------------------------------

def initialize_game_state(session):
    state = session.query(GameState).first()
    if not state:
        state = GameState(current_day='MON', current_week=1, current_month=4, current_year=2024)
        session.add(state)
        session.commit()
    return state


def load_active_player(session, state):
    if not state or not state.active_player_id:
        return None
    return session.get(Player, state.active_player_id)


def get_player_info(session, state):
    p = load_active_player(session, state)
    if p and p.school:
        last_first = " ".join(part for part in [getattr(p, 'last_name', ''), getattr(p, 'first_name', '')] if part).strip()
        display_name = last_first or p.name or "Unknown Player"
        return f"{display_name} ({p.position}) - {p.school.name} (Year {p.year})"
    return "Unknown Player"


_SIM_INTERRUPT_PATH = os.path.join(DATA_FOLDER, "sim_interrupts.json")
_DEFAULT_SIM_INTERRUPTS = {
    15: "Summer qualifiers demand manual coaching.",
    40: "Winter camp requires a player choice.",
    48: "Spring Senbatsu selections need your approval.",
}


def load_sim_interrupts():
    try:
        with open(_SIM_INTERRUPT_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            parsed = {int(k): str(v) for k, v in raw.items() if str(k).isdigit()}
            return parsed or dict(_DEFAULT_SIM_INTERRUPTS)
    except FileNotFoundError:
        return dict(_DEFAULT_SIM_INTERRUPTS)
    except Exception:
        return dict(_DEFAULT_SIM_INTERRUPTS)
    return dict(_DEFAULT_SIM_INTERRUPTS)


def run_smart_simulation(context, session, state, target_week: int):
    """Delegate consecutive weeks until an interrupt condition fires."""

    sim_interrupts = load_sim_interrupts()
    summaries = []
    reason = None

    while state.current_week < target_week:
        player = load_active_player(session, state)
        if not player:
            reason = "No active player loaded."
            break

        if state.current_week in sim_interrupts:
            reason = sim_interrupts[state.current_week]
            break

        # Story beats still deserve manual choices.
        if random.random() <= 0.40:
            reason = "Story event pending—take the reins."
            break

        user_school_id = player.school_id
        print(f"\r >> Processing Week {state.current_week}...", end="")
        simulate_background_matches(user_school_id, async_mode=True)

        context.refresh_session()
        context.set_player(player.id, user_school_id)
        _, summary = run_week_automatic(context, state.current_week)
        summaries.append(summary)
        if summary.stopped_by_interrupt:
            reason = summary.interrupt_reasons[-1] if summary.interrupt_reasons else "Week interrupted."
            break

        state.current_week += 1
        if state.current_week % 4 == 0:
            state.current_month += 1
            if state.current_month > 12:
                state.current_month = 1
        session.add(state)
        session.commit()

    print()
    return summaries, reason


def start_new_career_same_world():
    """Create a new first-year while keeping the current database intact."""
    session = get_session()
    try:
        state = initialize_game_state(session)
        ensure_world_population(session)

        active_player = load_active_player(session, state)
        if active_player:
            print(f"\nReplacing current lead: {active_player.name} will continue as an AI teammate.")

        confirm = input("Create a new first-year in the existing world? (y/n): ")
        if confirm.lower() != 'y':
            print("Cancelled new career setup.")
            time.sleep(1)
            return False

        new_id = create_hero(session)
        if not new_id:
            print("Character creation aborted.")
            time.sleep(1)
            return False

        state.active_player_id = new_id
        session.commit()
        print(f"{Colour.GREEN}New career ready. Jumping into the season...{Colour.RESET}")
        time.sleep(1)
        return True
    finally:
        session.close()


def rebuild_world_database():
    """Delete the active database file and create a clean world."""
    from config import DB_PATH

    if os.path.exists(DB_PATH):
        try:
            safe_delete_db(DB_PATH)
        except OSError as exc:
            print(f"{Colour.FAIL}Could not delete save: {exc}{Colour.RESET}")
            time.sleep(1)
            return False

    create_database()
    print(f"{Colour.GREEN}Database reset. Fresh world will be generated on next launch.{Colour.RESET}")
    time.sleep(1)
    return True


# -----------------------------------------------------
# MAIN MENU
# -----------------------------------------------------

def main_menu():
    while True:
        print_banner(MAIN_MENU_THEME)
        session = get_session()

        state = session.query(GameState).first()
        has_save = state is not None
        player_info = get_player_info(session, state) if has_save else "No Data"

        theme = choose_theme(MAIN_MENU_THEME)
        menu_lines = [
            f"{theme['muted']}Current Active Game: {Colour.CYAN}{player_info}{Colour.RESET}",
            "",
            f"{theme['accent']}[1]{Colour.RESET} Continue Active Game",
            f"{theme['accent']}[2]{Colour.RESET} Load Game (Select Slot)",
            f"{theme['accent']}[3]{Colour.RESET} New Career (Reuse Current World)",
            f"{theme['accent']}[4]{Colour.RESET} Rebuild World (Fresh Generation)",
            f"{theme['accent']}[5]{Colour.RESET} Exit",
        ]

        panel("Main Menu", menu_lines, theme=MAIN_MENU_THEME, width=70)

        choice = input("\nSelect: ")

        # -----------------------
        # CONTINUE GAME
        # -----------------------
        if choice == '1':
            session.close()
            run_game_loop()

        # -----------------------
        # LOAD GAME
        # -----------------------
        elif choice == '2':
            session.close()
            if show_save_menu("LOAD"):
                continue

        # -----------------------
        # NEW GAME
        # -----------------------
        elif choice == '3':
            session.close()
            if start_new_career_same_world():
                run_game_loop()

        # -----------------------
        # EXIT
        # -----------------------
        elif choice == '4':
            confirm = input(f"{Colour.RED}Rebuild entire world? This deletes all progress. (y/n): {Colour.RESET}")
            if confirm.lower() == 'y':
                session.close()
                if rebuild_world_database():
                    run_game_loop()
            else:
                session.close()

        elif choice == '5':
            sys.exit()

        session.close()


# -----------------------------------------------------
# GAME LOOP
# -----------------------------------------------------

def run_game_loop():
    session = get_session()
    context = GameContext(session_factory=get_session)
    session.expire_all()

    state = initialize_game_state(session)
    user_player = check_first_time_setup(session, state)
    if not user_player:
        print("ERROR: Player not created.")
        session.close()
        context.close_session()
        return

    user_school_id = user_player.school_id
    context.set_player(user_player.id, user_school_id)

    # -----------------------
    # MAIN WEEKLY LOOP
    # -----------------------
    try:
        while True:
            current_week = state.current_week

            user_player = load_active_player(session, state)
            if not user_player:
                print("ERROR: Active player not found.")
                break

            user_school_id = user_player.school_id
            context.set_player(user_player.id, user_school_id)

            print_banner()
            month_names = [
                "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
            ]
            month_label = month_names[(state.current_month - 1) % 12] if state.current_month else "--"
            print(f"{Colour.gold}>>> YEAR {state.current_year} | WEEK {current_week} / 50{Colour.RESET}")
            print(f"Date: {month_label} (Month {state.current_month})")

            # -----------------------------------------
            # SEASON END
            # -----------------------------------------
            if current_week > 50:
                print(f"\n{Colour.HEADER}=== SEASON {state.current_year} COMPLETE ==={Colour.RESET}")

                user_player = load_active_player(session, state)

                if user_player.year == 3:
                    print(f"\n{Colour.CYAN}CONGRATULATIONS ON YOUR GRADUATION!{Colour.RESET}")
                    print("Thank you for playing Koshien RPG.")
                    run_end_of_season_logic(user_player_id=context.player_id)
                    input("Press Enter to exit...")
                    break

                print("The third-years are retiring. Preparing for next season...")
                input("[Press Enter to Advance Year]")

                run_end_of_season_logic()

                session.expire_all()
                state = session.query(GameState).first()
                continue

            # -----------------------------------------
            # WORLD SIM EVENTS
            # -----------------------------------------
            print(f"{Colour.dim}Simulating world matches...{Colour.RESET}")
            simulate_background_matches(user_school_id)

            # -----------------------------------------
            # SUMMER QUALIFIERS
            # -----------------------------------------
            if current_week == 15:
                print(f"\n{Colour.RED}!!! THE SUMMER KOSHIEN QUALIFIERS !!!{Colour.RESET}")
                input("Press Enter to begin...")

                reps = run_season_qualifiers(user_school_id)
                user_qualified = any(s.id == user_school_id for s in reps)

                if user_qualified:
                    print(f"{Colour.gold}YOU WON THE PREFECTURE!{Colour.RESET}")
                    run_koshien_tournament(user_school_id, reps)
                else:
                    print(f"{Colour.FAIL}Eliminated in qualifiers.{Colour.RESET}")
                    run_koshien_tournament(user_school_id, reps)

            # -----------------------------------------
            # WINTER CAMP
            # -----------------------------------------
            if current_week == 40:
                print(f"\n{Colour.WARNING}Winter Training Camp begins.{Colour.RESET}")
                if input("Participate? (y/n): ").lower() == 'y':
                    run_training_camp_event(context)
                else:
                    print("You skipped camp.")

            # -----------------------------------------
            # SPRING KOSHIEN
            # -----------------------------------------
            if current_week == 48:
                print(f"\n{Colour.CYAN}Spring Senbatsu Approaches.{Colour.RESET}")
                run_spring_koshien(user_school_id)

            # -----------------------------------------
            # TRAINING WEEK
            # -----------------------------------------
            context.refresh_session()
            context.set_player(user_player.id, user_school_id)
            print(f"{Colour.dim}Opening schedule...{Colour.RESET}")
            start_week(context, current_week)

            # -----------------------------------------
            # MENU
            # -----------------------------------------
            print("\nOptions:")
            print(" [Enter] Next Week")
            print(" [S] Scouting / Roster")
            print(" [D] Save Game")
            print(" [A] Smart Sim (Delegate Weeks)")
            print(" [Q] Quit to Menu")

            cmd = input(">> ").lower()

            if cmd == 's':
                from ui.scouting_report import view_scouting_menu
                view_scouting_menu(context)
                continue
            elif cmd == 'd':
                show_save_menu("SAVE")
                continue
            elif cmd == 'a':
                target_input = input(
                    f"Simulate until week (>{state.current_week}): "
                ).strip()
                try:
                    target_week = int(target_input) if target_input else state.current_week + 1
                except ValueError:
                    print("Invalid week.")
                    continue
                if target_week <= state.current_week:
                    target_week = state.current_week + 1
                target_week = min(50, target_week)
                # Advance once before automation, mirroring the normal flow.
                state.current_week += 1
                if state.current_week % 4 == 0:
                    state.current_month += 1
                    if state.current_month > 12:
                        state.current_month = 1
                session.commit()
                if state.current_week >= target_week:
                    continue
                summaries, reason = run_smart_simulation(context, session, state, target_week)
                if summaries:
                    render_weekly_dashboard(summaries[-1])
                    input()
                if reason:
                    print(f"\n{Colour.WARNING}Smart Sim stopped: {reason}{Colour.RESET}")
                    input("Press Enter to continue...")
                session.refresh(state)
                continue
            elif cmd == 'q':
                break

            # Advance week
            state.current_week += 1

            if state.current_week % 4 == 0:
                state.current_month += 1
                if state.current_month > 12:
                    state.current_month = 1

            session.commit()
    finally:
        session.close()
        context.close_session()


# -----------------------------------------------------
# MAIN ENTRY
# -----------------------------------------------------

def main():
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nGame Exited.")

if __name__ == "__main__":
    main()