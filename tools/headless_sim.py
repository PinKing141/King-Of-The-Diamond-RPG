import argparse
import logging
import random

from core.game_context import GameContext
from core.services import SessionProvider
from database.populate_japan import populate_world
from database.setup_db import GameState, Player, School, create_database, get_session
from game.loop.weekly_scheduler import run_week_automatic


def _ensure_state(session) -> GameState:
    state = session.query(GameState).first()
    if not state:
        state = GameState(current_day="MON", current_week=1, current_month=4, current_year=2024)
        session.add(state)
        session.commit()
    return state


def _ensure_player(session, state: GameState) -> Player:
    if not state.active_player_id:
        raise RuntimeError("Active player not set; create a save before running headless sim.")
    player = session.get(Player, state.active_player_id)
    if not player:
        raise RuntimeError("Active player record missing; cannot run headless sim.")
    return player


def _maybe_populate_world(session, threshold: int = 10) -> None:
    try:
        school_count = session.query(School).count()
    except Exception as exc:
        raise RuntimeError(f"Failed to read schools: {exc}") from exc
    if school_count >= threshold:
        return
    populate_world()


def run_headless_season(weeks: int, seed: int | None = None, *, auto_world: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    logger = logging.getLogger("headless_sim")

    create_database()
    provider = SessionProvider(get_session)
    session = provider.get()
    state = _ensure_state(session)
    if auto_world:
        _maybe_populate_world(session)
    player = _ensure_player(session, state)

    context = GameContext(session_factory=provider.get, session_provider=provider)
    context.set_player(player.id, player.school_id)

    base_seed = seed if seed is not None else random.randint(0, 10_000_000)
    logger.info("Starting headless simulation for %s weeks (seed=%s)", weeks, base_seed)

    for i in range(weeks):
        week_seed = base_seed + i
        execution, summary = run_week_automatic(context, state.current_week, rng_seed=week_seed)
        state.current_week += 1
        session.commit()
        logger.info(
            "Week %s complete: fatigue=%s warnings=%s highlights=%s",
            summary.week_number,
            getattr(context.session.get(Player, context.player_id), "fatigue", "-"),
            len(summary.warnings),
            len(summary.highlights),
        )
        if summary.stopped_by_interrupt:
            logger.warning("Simulation stopped early: %s", "; ".join(summary.interrupt_reasons or []))
            break

    provider.close()


def main():
    parser = argparse.ArgumentParser(description="Run headless season simulation")
    parser.add_argument("--weeks", type=int, default=4, help="Number of weeks to simulate")
    parser.add_argument("--seed", type=int, default=None, help="Base RNG seed for deterministic runs")
    parser.add_argument("--auto-world", action="store_true", help="Populate world if schools are missing")
    args = parser.parse_args()

    run_headless_season(weeks=args.weeks, seed=args.seed, auto_world=args.auto_world)


if __name__ == "__main__":
    main()
