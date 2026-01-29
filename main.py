import sys
import os
from functools import partial
from database.setup_db import create_database, GameState, School, Player, get_session, safe_delete_db
from database.populate_japan import populate_world, prefecture_counts
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
from ui.tui_main_menu import run_tui_main_menu
from ui.tui_world_gen import run_tui_world_gen


MAIN_MENU_THEME = DEFAULT_THEME


def ensure_world_population(session, view: SeasonView):
    """Ensure the database has a populated world map."""
    try:
        school_count = session.query(School).count()
    except Exception as exc:
        view.display_error(f"Failed to read schools: {exc}")
        raise

    if school_count < 10:
        # Optional Textual overlay for world generation.
        use_tui_world = os.environ.get("USE_TUI_WORLD_LOADING", "").lower() in {"1", "true", "yes"} or os.environ.get("USE_TUI_MAIN_MENU", "").lower() in {"1", "true", "yes"}
        if use_tui_world:
            import queue

            progress_q: queue.Queue[tuple[str, int, int]] = queue.Queue()

            def _gen_world():
                populate_world(progress_cb=lambda pref, idx, total: progress_q.put((pref, idx, total)))

            ran = run_tui_world_gen(_gen_world, progress_queue=progress_q)
            if ran is None:
                # Fallback if TUI unavailable
                view.announce_world_gen()
                populate_world()
                view.announce_world_gen_complete()
            else:
                # Already executed inside the TUI app.
                view.display_info("World generation finished.")
        else:
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

    setattr(state, "active_player_id", new_id)
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

        setattr(state, "active_player_id", new_id)
        session.commit()
        view.announce_new_career_ready()
        return True
    finally:
        if owns_session:
            session.close()


def rebuild_world_database(view: SeasonView):
    """Delete the active database file and create a clean world."""
    def _do_rebuild() -> bool:
        if os.path.exists(DB_PATH):
            try:
                safe_delete_db(DB_PATH)
            except OSError as exc:
                view.display_error(f"Could not delete save: {exc}")
                return False
        create_database()
        with get_session() as session:
            ensure_world_population(session, view)
        return True

    use_tui = os.environ.get("USE_TUI_REBUILD", "").lower() in {"1", "true", "yes"} or os.environ.get("USE_TUI_WORLD_LOADING", "").lower() in {"1", "true", "yes"} or os.environ.get("USE_TUI_MAIN_MENU", "").lower() in {"1", "true", "yes"}
    if use_tui:
        try:
            from ui.tui_rebuild_world import run_tui_rebuild_world

            res = run_tui_rebuild_world(_do_rebuild)
            if res is not None:
                if res:
                    view.display_info("Database reset and world regenerated. Returning to main menu...")
                else:
                    view.display_error("Rebuild failed or cancelled.")
                return bool(res)
        except Exception:
            pass

    # Fallback: console flow
    if os.path.exists(DB_PATH):
        try:
            safe_delete_db(DB_PATH)
        except OSError as exc:
            view.display_error(f"Could not delete save: {exc}")
            return False

    create_database()

    # Immediately generate a fresh world so the main menu can resume without jumping into creation.
    with get_session() as session:
        ensure_world_population(session, view)
    view.display_info("Database reset and world regenerated. Returning to main menu...")
    return True


def launch_game_engine(view: SeasonView, *, session=None, session_provider: SessionProvider | None = None):
    """Bootstraps the GameContext and hands off to the SeasonManager."""

    # Ensure DB and migrations are applied for direct callers (legacy paths may bypass main_menu).
    create_database()

    provider = session_provider or SessionProvider(get_session, initial_session=session)
    owns_provider = session_provider is None
    session = session or provider.get()
    context = GameContext(session_factory=provider.get, session_provider=provider)
    # Pre-register commentary listener using the current IO without capturing via lambda defaults.
    context.match_event_listeners = (partial(attach_commentary_listener, io=view.io),)
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
        while True:
            # The game engine closes sessions when it exits; always fetch a fresh one.
            session = provider.get()
            state = session.query(GameState).first()
            has_save = state is not None
            player_info = get_player_info(session, state) if has_save else "No Data"

            choice = None
            used_tui_menu = False
            if os.environ.get("USE_TUI_MAIN_MENU", "").lower() in {"1", "true", "yes"}:
                try:
                    choice = run_tui_main_menu(player_info=player_info, has_save=has_save)
                    used_tui_menu = choice is not None
                except Exception as exc:
                    # Fall back to console menu if TUI fails.
                    view.display_error(f"TUI menu failed ({exc}); using console menu.")
                    choice = None

            if choice is None:
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
                confirmed = False
                if used_tui_menu:
                    try:
                        from ui.tui_confirm import run_tui_confirm

                        res = run_tui_confirm("Rebuild the world database? This will delete existing saves.")
                        if res is None:
                            view.display_error("TUI confirm unavailable; rebuild cancelled.")
                            continue
                        confirmed = bool(res)
                    except Exception:
                        view.display_error("TUI confirm failed; rebuild cancelled.")
                        continue
                if not confirmed:
                    confirmed = view.prompt_rebuild_world()
                if confirmed:
                    if rebuild_world_database(view):
                        provider.close()
                        provider = SessionProvider(get_session)
                        session = provider.get()
                        # After regeneration, stay in main menu (no auto-launch/character creation).
                        continue
            elif choice == "5":
                break
    finally:
        provider.close()


def run_game_loop():
    """Backwards compatibility wrapper for older entry points."""
    view = ConsoleView(theme=MAIN_MENU_THEME)
    # Guard to avoid crashing on clean installs when invoked directly.
    create_database()
    launch_game_engine(view)


def main():
    try:
        view = ConsoleView(theme=MAIN_MENU_THEME)
        main_menu(view)
    except KeyboardInterrupt:
        print("\n\nGame Exited.")


if __name__ == "__main__":
    main()
