import sys
import os
import time
from sqlalchemy.orm import sessionmaker
from database.setup_db import engine, create_database, GameState, School, Player, Coach
from ui.ui_display import Colour, clear_screen
from game.weekly_scheduler import start_week
from world_sim.tournament_sim import run_koshien_tournament, run_spring_koshien
from world_sim.qualifiers import run_season_qualifiers
from world_sim.prefecture_engine import simulate_background_matches
from world.coach_generation import generate_coach_for_school
from world.school_philosophy import get_philosophy
from game.create_player import create_hero 
from game.season_engine import run_end_of_season_logic
from game.training_logic import run_training_camp_event
from game.save_manager import show_save_menu 
from utils import PLAYER_ID, set_player_id

# Ensure database tables exist
create_database()
Session = sessionmaker(bind=engine)


# -----------------------------------------------------
# UI
# -----------------------------------------------------

def print_banner():
    clear_screen()
    print(f"{Colour.HEADER}=========================================={Colour.RESET}")
    print(f"{Colour.HEADER}       ⚾  KŌSHIEN RPG: THE FINAL  ⚾     {Colour.RESET}")
    print(f"{Colour.HEADER}=========================================={Colour.RESET}")
    print("     The Road to the Sacred Stadium begins here.\n")


# -----------------------------------------------------
# FIRST TIME SETUP
# -----------------------------------------------------

def check_first_time_setup(session):
    """Populate world and create player if needed."""

    # 1. World population
    try:
        school_count = session.query(School).count()
    except:
        school_count = 0

    if school_count < 10:
        print(f"{Colour.WARNING}World not populated. Running World Generator...{Colour.RESET}")
        from database.populate_japan import populate_world
        populate_world()
        print(f"{Colour.GREEN}World Generation Complete.{Colour.RESET}")
        time.sleep(1)

    # 2. Player creation
    player = session.get(Player, PLAYER_ID) if PLAYER_ID else None
    if not player:
        print(f"\n{Colour.CYAN}No player data found. Starting Character Creation...{Colour.RESET}")
        time.sleep(1)
        new_id = create_hero()
        set_player_id(new_id)
        print(f"{Colour.GREEN}Player Created. Welcome to High School Baseball.{Colour.RESET}")
        time.sleep(1)


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


def get_player_info(session):
    p = session.get(Player, PLAYER_ID) if PLAYER_ID else None
    if p and p.school:
        return f"{p.name} ({p.position}) - {p.school.name} (Year {p.year})"
    return "Unknown Player"


# -----------------------------------------------------
# MAIN MENU
# -----------------------------------------------------

def main_menu():
    while True:
        print_banner()
        session = Session()

        has_save = session.query(GameState).first() is not None
        player_info = get_player_info(session) if has_save else "No Data"

        print(f"Current Active Game: {Colour.CYAN}{player_info}{Colour.RESET}\n")

        print("1. Continue Active Game")
        print("2. Load Game (Select Slot)")
        print("3. New Game (Resets Everything)")
        print("4. Exit")

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
            confirm = input(f"{Colour.RED}Are you sure? This deletes all progress. (y/n): {Colour.RESET}")
            if confirm.lower() == 'y':
                session.close()

                from config import DB_PATH
                if os.path.exists(DB_PATH):
                    try:
                        os.remove(DB_PATH)
                    except:
                        pass

                print(f"{Colour.GREEN}Save deleted. Restarting fresh world...{Colour.RESET}")
                time.sleep(1)

                # Rebuild database
                create_database()

                # Reset session + PLAYER_ID
                set_player_id(None)
                Session.configure(bind=engine)
                session = Session()

                # Run setup from scratch
                check_first_time_setup(session)
                run_game_loop()

        # -----------------------
        # EXIT
        # -----------------------
        elif choice == '4':
            sys.exit()

        session.close()


# -----------------------------------------------------
# GAME LOOP
# -----------------------------------------------------

def run_game_loop():
    session = Session()
    session.expire_all()

    check_first_time_setup(session)
    state = initialize_game_state(session)

    # Load player safely
    user_player = session.get(Player, PLAYER_ID) if PLAYER_ID else None
    if not user_player:
        check_first_time_setup(session)
        user_player = session.get(Player, PLAYER_ID)
        if not user_player:
            print("ERROR: Player not created.")
            return

    user_school_id = user_player.school_id
    conn = engine.raw_connection()

    # -----------------------
    # MAIN WEEKLY LOOP
    # -----------------------
    while True:
        current_week = state.current_week

        print_banner()
        print(f"{Colour.gold}>>> YEAR {state.current_year} | WEEK {current_week} / 50{Colour.RESET}")
        print(f"Month: {state.current_month}")

        # -----------------------------------------
        # SEASON END
        # -----------------------------------------
        if current_week > 50:
            print(f"\n{Colour.HEADER}=== SEASON {state.current_year} COMPLETE ==={Colour.RESET}")

            user_player = session.get(Player, PLAYER_ID)

            if user_player.year == 3:
                print(f"\n{Colour.CYAN}CONGRATULATIONS ON YOUR GRADUATION!{Colour.RESET}")
                print("Thank you for playing Koshien RPG.")
                run_end_of_season_logic(user_player_id=PLAYER_ID)
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
                run_training_camp_event(conn)
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
        start_week(current_week)

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
            view_scouting_menu()
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


# -----------------------------------------------------
# MAIN ENTRY
# -----------------------------------------------------

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nGame Exited.")