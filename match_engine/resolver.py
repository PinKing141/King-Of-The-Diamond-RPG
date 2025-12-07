"""Match resolution helpers extracted from match_sim to avoid circular imports."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Any, Dict, Optional

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
    except Exception:
        return "Error"

    return score_str


def _simulate_match(
    home_team,
    away_team,
    tournament_name: str,
    *,
    silent: bool,
    fast: bool,
    clutch_pitch: Optional[Dict[str, Any]] = None,
    rival_match_context=None,
    rival_presentation=None,
    persist_results: bool = True,
):
    auto_play_inputs = fast or silent
    human_team_ids = [] if auto_play_inputs else None

    if fast:
        winner = engine_run_match(
            home_team.id,
            away_team.id,
            fast=True,
            auto_play_inputs=auto_play_inputs,
            persist_results=persist_results,
            clutch_pitch=clutch_pitch,
            tournament_name=tournament_name,
            human_team_ids=human_team_ids,
            rival_match_context=rival_match_context,
            rival_presentation=rival_presentation,
        )
    elif silent:
        with _suppress_print():
            winner = engine_run_match(
                home_team.id,
                away_team.id,
                auto_play_inputs=auto_play_inputs,
                clutch_pitch=clutch_pitch,
                tournament_name=tournament_name,
                persist_results=persist_results,
                human_team_ids=human_team_ids,
                rival_match_context=rival_match_context,
                rival_presentation=rival_presentation,
            )
    else:
        winner = engine_run_match(
            home_team.id,
            away_team.id,
            auto_play_inputs=auto_play_inputs,
            clutch_pitch=clutch_pitch,
            tournament_name=tournament_name,
            persist_results=persist_results,
            human_team_ids=human_team_ids,
            rival_match_context=rival_match_context,
            rival_presentation=rival_presentation,
        )

    score_str = _fetch_latest_score(home_team.id, away_team.id, tournament_name)
    with session_scope() as session:
        consume_strategy_mods(session, home_team.id)
        consume_strategy_mods(session, away_team.id)

    return winner, score_str


_RESOLVE_MODE_PRESETS: Dict[str, Dict[str, bool]] = {
    "standard": {"fast": False, "silent": False},
    "interactive": {"fast": False, "silent": False},
    "fast": {"fast": True, "silent": False},
    "silent": {"fast": False, "silent": True},
}


def resolve_match(
    home_team,
    away_team,
    tournament_name: str = "Practice Match",
    *,
    mode: str = "standard",
    silent: Optional[bool] = None,
    clutch_pitch: Optional[Dict[str, Any]] = None,
    rival_match_context=None,
    rival_presentation=None,
    persist_results: bool = True,
):
    """Unified entry point for orchestrating a simulated match."""

    preset = _RESOLVE_MODE_PRESETS.get(mode)
    if preset is None:
        raise ValueError(f"Unknown resolve mode '{mode}'.")
    fast = preset["fast"]
    effective_silent = preset["silent"] if silent is None else silent
    winner = _simulate_match(
        home_team,
        away_team,
        tournament_name,
        silent=effective_silent,
        fast=fast,
        clutch_pitch=clutch_pitch,
        rival_match_context=rival_match_context,
        rival_presentation=rival_presentation,
        persist_results=persist_results,
    )
    return winner


__all__ = ["resolve_match"]
