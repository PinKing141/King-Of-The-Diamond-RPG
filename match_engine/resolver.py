"""Compatibility resolver wrappers for match execution (used by legacy tests)."""
from __future__ import annotations

from match_engine.controller import (
	_fetch_latest_score,
	resolve_match,
	run_match as engine_run_match,
)
from database.setup_db import session_scope
from game.coach_strategy import consume_strategy_mods

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
):
	"""Thin shim over controller.run_match that preserves legacy monkeypatch points."""

	effective_auto = auto_play_inputs or silent or fast
	managed_session = False
	db_session = session
	if db_session is None:
		managed_session = True
		ctx = session_scope()
		db_session = ctx.__enter__()

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
	)

	score_str = _fetch_latest_score(home_team.id, away_team.id, tournament_name, session=db_session)
	consume_strategy_mods(db_session, home_team.id)
	consume_strategy_mods(db_session, away_team.id)

	if managed_session:
		ctx.__exit__(None, None, None)

	return winner, score_str


__all__ = [
	"resolve_match",
	"_simulate_match",
	"engine_run_match",
	"session_scope",
	"consume_strategy_mods",
	"_fetch_latest_score",
]
