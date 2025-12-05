import sys
import os
import time

from core.event_bus import EventBus
from database.setup_db import create_database, GameState, School, Player, get_session
from ui.ui_display import Colour, clear_screen
from game.weekly_scheduler import start_week
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

# Ensure database tables exist
create_database()

# Event bus + analytics initialisation
GLOBAL_EVENT_BUS = initialise_analytics(EventBus())

# -----------------------------------------------------
# UI
# -----------------------------------------------------

def print_banner():
    clear_screen()
    print(f"{Colour.HEADER}==============================================={Colour.RESET}")
    print(f"{Colour.HEADER}   ⚾  KING OF THE DIAMOND RPG: THE FINAL  ⚾     {Colour.RESET}")
    print(f"{Colour.HEADER}==============================================={Colour.RESET}")
    print("     The Road to the Sacred Stadium begins here.\n")


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
        return f"{p.name} ({p.position}) - {p.school.name} (Year {p.year})"
    return "Unknown Player"


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
            os.remove(DB_PATH)
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
        print_banner()
        session = get_session()

        state = session.query(GameState).first()
        has_save = state is not None
        player_info = get_player_info(session, state) if has_save else "No Data"

        print(f"Current Active Game: {Colour.CYAN}{player_info}{Colour.RESET}\n")

        print("1. Continue Active Game")
        print("2. Load Game (Select Slot)")
        print("3. New Career (Reuse Current World)")
        print("4. Rebuild World (Fresh Generation)")
        print("5. Exit")

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
            print(f"{Colour.gold}>>> YEAR {state.current_year} | WEEK {current_week} / 50{Colour.RESET}")
            print(f"Month: {state.current_month}")

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
            start_week(context, current_week)

            # -----------------------------------------
            # MENU
            # -----------------------------------------
            print("\nOptions:")
            print(" [Enter] Next Week")
            print(" [S] Scouting / Roster")
            print(" [D] Save Game")
            print(" [Q] Quit to Menu")

            cmd = input(">> ").lower()

            if cmd == 's':
                from ui.scouting_report import view_scouting_menu
                view_scouting_menu(context)
                continue
            elif cmd == 'd':
                show_save_menu("SAVE")
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