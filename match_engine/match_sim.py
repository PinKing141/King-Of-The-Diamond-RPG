"""Bridging helpers for running simulated matches in various modes."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager

from database.setup_db import Game, session_scope
from game.coach_strategy import consume_strategy_mods

from .controller import run_match as engine_run_match


@contextmanager
def _suppress_print():
    """Temporarily silence stdout for background simulations."""
    original_stdout = sys.stdout
    devnull = open(os.devnull, "w", encoding="utf-8")
    try:
        sys.stdout = devnull
        yield
    finally:
        sys.stdout = original_stdout
        devnull.close()


def _fetch_latest_score(home_id: int, away_id: int, tournament_name: str) -> str:
    """Read the latest game for the two teams and optionally tag the tournament."""
    score_str = "0 - 0"
    try:
        with session_scope() as session:
            game = (
                session.query(Game)
                .filter(
                    Game.home_school_id == home_id,
                    Game.away_school_id == away_id,
                )
                .order_by(Game.id.desc())
                .first()
            )
            if not game:
                return score_str

            score_str = f"{game.away_score} - {game.home_score}"
            if tournament_name != "Practice Match" and game.tournament != tournament_name:
                game.tournament = tournament_name
                session.commit()
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"Error retrieving match result: {exc}")
        return "Error"

    return score_str


def _simulate_match(home_team, away_team, tournament_name: str, *, silent: bool, fast: bool):
    """Shared runner used by both traditional and fast simulations."""
    if fast:
        winner = engine_run_match(home_team.id, away_team.id, fast=True)
    elif silent:
        with _suppress_print():
            winner = engine_run_match(home_team.id, away_team.id)
    else:
        winner = engine_run_match(home_team.id, away_team.id)

    score_str = _fetch_latest_score(home_team.id, away_team.id, tournament_name)
    with session_scope() as session:
        consume_strategy_mods(session, home_team.id)
        consume_strategy_mods(session, away_team.id)
    return winner, score_str


def sim_match(home_team, away_team, tournament_name: str = "Practice Match", silent: bool = False):
    """Legacy bridge for running a match with optional suppressed commentary."""
    return _simulate_match(home_team, away_team, tournament_name, silent=silent, fast=False)


def sim_match_fast(home_team, away_team, tournament_name: str = "Practice Match"):
    """High-throughput simulation that skips commentary generation entirely."""
    return _simulate_match(home_team, away_team, tournament_name, silent=False, fast=True)


__all__ = ["sim_match", "sim_match_fast"]
