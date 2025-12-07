import sys
import os
import time

from database.setup_db import create_database, GameState, School, Player, get_session, safe_delete_db
from database.populate_japan import populate_world
from ui.ui_display import Colour, clear_screen
from ui.ui_core import choose_theme, panel, DEFAULT_THEME
from game.personnel.create_player import create_hero
from game.save_manager import show_save_menu
from core.game_context import GameContext
from game.loop.season_manager import SeasonManager
from config import DB_PATH


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


def ensure_world_population(session):
    """Ensure the database has a populated world map."""
    try:
        school_count = session.query(School).count()
    except Exception:
        school_count = 0

    if school_count < 10:
        print(f"{Colour.WARNING}World not populated. Running World Generator...{Colour.RESET}")
        populate_world()
        print(f"{Colour.GREEN}World Generation Complete.{Colour.RESET}")
        time.sleep(1)


def check_first_time_setup(session, state):
    """Populate world and ensure an active player exists."""

    ensure_world_population(session)

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


def initialize_game_state(session):
    state = session.query(GameState).first()
    if not state:
        state = GameState(current_day="MON", current_week=1, current_month=4, current_year=2024)
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
        last_first = " ".join(part for part in [getattr(p, "last_name", ""), getattr(p, "first_name", "")] if part).strip()
        display_name = last_first or p.name or "Unknown Player"
        return f"{display_name} ({p.position}) - {p.school.name} (Year {p.year})"
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
        if confirm.lower() != "y":
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


def launch_game_engine():
    """Bootstraps the GameContext and hands off to the SeasonManager."""
    session = get_session()
    context = GameContext(session_factory=get_session)
    session.expire_all()

    try:
        state = initialize_game_state(session)
        user_player = check_first_time_setup(session, state)
        if not user_player:
            print("ERROR: Player not created.")
            return

        manager = SeasonManager(context, session, theme=MAIN_MENU_THEME)
        manager.run_season_loop()
    finally:
        session.close()
        context.close_session()


def main_menu():
    create_database()
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
        session.close()

        if choice == "1":
            launch_game_engine()
        elif choice == "2":
            if show_save_menu("LOAD"):
                continue
        elif choice == "3":
            if start_new_career_same_world():
                launch_game_engine()
        elif choice == "4":
            confirm = input(f"{Colour.RED}Rebuild entire world? This deletes all progress. (y/n): {Colour.RESET}")
            if confirm.lower() == "y":
                if rebuild_world_database():
                    launch_game_engine()
        elif choice == "5":
            sys.exit()


def run_game_loop():
    """Backwards compatibility wrapper for older entry points."""
    launch_game_engine()


def main():
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nGame Exited.")


if __name__ == "__main__":
    main()