import sys
import os

from database.setup_db import create_database, GameState, School, Player, get_session, safe_delete_db
from database.populate_japan import populate_world
from ui.ui_core import DEFAULT_THEME
from game.personnel.create_player import create_hero
from game.save_manager import show_save_menu
from core.game_context import GameContext
from core.services import SessionProvider
from game.loop.season_manager import SeasonManager
from game.interfaces import SeasonView
from ui.console_view import ConsoleView
from config import DB_PATH
from ui.match_commentary import attach_commentary_listener


MAIN_MENU_THEME = DEFAULT_THEME


def ensure_world_population(session, view: SeasonView):
    """Ensure the database has a populated world map."""
    try:
        school_count = session.query(School).count()
    except Exception as exc:
        view.display_error(f"Failed to read schools: {exc}")
        raise

    if school_count < 10:
        view.announce_world_gen()
        populate_world()
        view.announce_world_gen_complete()


def check_first_time_setup(session, state, view: SeasonView):
    """Populate world and ensure an active player exists."""

    ensure_world_population(session, view)

    player = load_active_player(session, state)
    if player:
        return player

    view.announce_character_creation()
    new_id = create_hero(session)
    if not new_id:
        return None

    state.active_player_id = new_id
    session.commit()

    view.announce_player_created()

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


def start_new_career_same_world(view: SeasonView, *, session=None):
    """Create a new first-year while keeping the current database intact."""
    owns_session = session is None
    session = session or get_session()
    try:
        state = initialize_game_state(session)
        ensure_world_population(session, view)

        active_player = load_active_player(session, state)
        if active_player:
            view.display_info(f"\nReplacing current lead: {active_player.name} will continue as an AI teammate.")

        if not view.prompt_new_career():
            view.display_info("Cancelled new career setup.")
            return False

        new_id = create_hero(session)
        if not new_id:
            view.display_info("Character creation aborted.")
            return False

        state.active_player_id = new_id
        session.commit()
        view.announce_new_career_ready()
        return True
    finally:
        if owns_session:
            session.close()


def rebuild_world_database(view: SeasonView):
    """Delete the active database file and create a clean world."""
    if os.path.exists(DB_PATH):
        try:
            safe_delete_db(DB_PATH)
        except OSError as exc:
            view.display_error(f"Could not delete save: {exc}")
            return False

    create_database()
    view.display_info("Database reset. Fresh world will be generated on next launch.")
    return True


def launch_game_engine(view: SeasonView, *, session=None, session_provider: SessionProvider | None = None):
    """Bootstraps the GameContext and hands off to the SeasonManager."""

    provider = session_provider or SessionProvider(get_session, initial_session=session)
    owns_provider = session_provider is None
    session = session or provider.get()
    context = GameContext(session_factory=provider.get, session_provider=provider)
    context.match_event_listeners = (lambda bus, io=view.io: attach_commentary_listener(bus, io=io),)
    session.expire_all()

    try:
        state = initialize_game_state(session)
        user_player = check_first_time_setup(session, state, view)
        if not user_player:
            view.display_error("ERROR: Player not created.")
            return

        manager = SeasonManager(context, session, view=view, session_provider=provider)
        manager.run_season_loop()
    finally:
        if owns_provider:
            provider.close()
        context.close_session()


def main_menu(view: ConsoleView, *, session=None, session_provider: SessionProvider | None = None):
    create_database()
    provider = session_provider or SessionProvider(get_session, initial_session=session)

    try:
        session = provider.get()
        while True:
            state = session.query(GameState).first()
            has_save = state is not None
            player_info = get_player_info(session, state) if has_save else "No Data"

            choice = view.prompt_main_menu(player_info=player_info, has_save=has_save)
            session.expire_all()

            if choice == "1":
                launch_game_engine(view, session=session, session_provider=provider)
            elif choice == "2":
                if show_save_menu("LOAD"):
                    provider.close()
                    provider = SessionProvider(get_session)
                    session = provider.get()
                    continue
            elif choice == "3":
                if start_new_career_same_world(view, session=session):
                    launch_game_engine(view, session=session, session_provider=provider)
            elif choice == "4":
                if view.prompt_rebuild_world():
                    if rebuild_world_database(view):
                        provider.close()
                        provider = SessionProvider(get_session)
                        session = provider.get()
                        launch_game_engine(view, session=session, session_provider=provider)
            elif choice == "5":
                break
    finally:
        provider.close()


def run_game_loop():
    """Backwards compatibility wrapper for older entry points."""
    view = ConsoleView(theme=MAIN_MENU_THEME)
    launch_game_engine(view)


def main():
    try:
        view = ConsoleView(theme=MAIN_MENU_THEME)
        main_menu(view)
    except KeyboardInterrupt:
        print("\n\nGame Exited.")


if __name__ == "__main__":
    main()