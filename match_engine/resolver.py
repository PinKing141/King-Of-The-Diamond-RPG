"""Compatibility resolver wrappers for match execution (legacy; prefer controller.resolve_match).

This module is kept only for backward compatibility. New callers should import
from match_engine.controller or match_engine.resolve_match via the facade.
"""
from __future__ import annotations

import warnings

from match_engine.controller import (
	_fetch_latest_score,
	resolve_match,
	run_match as engine_run_match,
)
from game.coach_strategy import consume_strategy_mods
from core.io_interface import NoOpIO, IOInterface

warnings.warn(
	"match_engine.resolver is deprecated; use match_engine.controller.resolve_match instead",
	DeprecationWarning,
	stacklevel=2,
)

def _simulate_match(
	home_team,
	away_team,
	tournament_name: str,
	*,
	silent: bool = False,
	fast: bool = False,
	auto_play_inputs: bool = False,
	persist_results: bool = True,
	clutch_pitch=None,
	human_team_ids=None,
	rival_match_context=None,
	rival_presentation=None,
	session=None,
	event_listeners=None,
	io: IOInterface | None = None,
):
	"""Thin shim over controller.run_match that preserves legacy monkeypatch points."""

	if session is None:
		raise ValueError("session is required for match simulation")
	effective_io = io or (NoOpIO() if (silent or fast) else None)

	effective_auto = auto_play_inputs or silent or fast
	db_session = session

	winner = engine_run_match(
		home_team.id,
		away_team.id,
		silent=silent,
		fast=fast,
		auto_play_inputs=effective_auto,
		clutch_pitch=clutch_pitch,
		tournament_name=tournament_name,
		persist_results=persist_results,
		human_team_ids=human_team_ids,
		rival_match_context=rival_match_context,
		rival_presentation=rival_presentation,
		session=db_session,
		io=effective_io,
		event_listeners=event_listeners,
	)

	score_str = _fetch_latest_score(home_team.id, away_team.id, tournament_name, session=db_session)
	consume_strategy_mods(db_session, home_team.id)
	consume_strategy_mods(db_session, away_team.id)

	return winner, score_str


__all__ = [
	"resolve_match",
	"_simulate_match",
	"engine_run_match",
	"consume_strategy_mods",
	"_fetch_latest_score",
]
