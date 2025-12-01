"""Helpers for assembling shared match context dictionaries."""
"""Helpers for assembling shared at-bat context dictionaries."""
from __future__ import annotations

from typing import Dict, List, Optional


def _team_score(state, team_id: Optional[int]) -> int:
	if not state or team_id is None:
		return 0
	if getattr(state.home_team, "id", None) == team_id:
		return getattr(state, "home_score", 0) or 0
	return getattr(state, "away_score", 0) or 0


def _player_team_id(player) -> Optional[int]:
	if not player:
		return None
	return getattr(player, "team_id", getattr(player, "school_id", None))


def _lineup_slot(player) -> Optional[int]:
	if not player:
		return None
	slot = getattr(player, "_lineup_slot", None)
	if slot:
		return slot
	return getattr(player, "lineup_position", None)


def get_at_bat_context(state, batter, pitcher) -> Dict[str, object]:
	"""Return a normalized dictionary summarizing the current plate appearance."""
	inning = getattr(state, "inning", 1) or 1
	top_half = getattr(state, "top_bottom", "Top") == "Top"
	offense_team_id = getattr(state.away_team, "id", None) if top_half else getattr(state.home_team, "id", None)
	defense_team_id = getattr(state.home_team, "id", None) if top_half else getattr(state.away_team, "id", None)
	batter_team_id = _player_team_id(batter)
	pitcher_team_id = _player_team_id(pitcher)
	offense_score = _team_score(state, offense_team_id)
	defense_score = _team_score(state, defense_team_id)
	score_diff = offense_score - defense_score

	runners = list(getattr(state, "runners", [None, None, None]) or [None, None, None])
	is_risp = any(runners[1:])
	bases_loaded = all(base is not None for base in runners)

	pitch_count = 0
	if pitcher and getattr(pitcher, "id", None) is not None:
		pitch_count = getattr(state, "pitch_counts", {}).get(pitcher.id, 0)

	pressure_margin = getattr(state, "pressure_margin", 2)
	is_late = inning >= 7
	is_close = abs(score_diff) <= (pressure_margin or 2)
	is_clutch = is_late and is_close

	batter_hand = getattr(batter, "bat_hand", getattr(batter, "bats", "R"))
	pitcher_hand = getattr(pitcher, "throws", getattr(pitcher, "pitch_hand", "R"))

	lineup_slot = _lineup_slot(batter)

	pressure_state = "high" if (is_clutch or is_risp) else "normal"

	context: Dict[str, object] = {
		"inning": inning,
		"top_half": top_half,
		"score_diff": score_diff,
		"offense_score": offense_score,
		"defense_score": defense_score,
		"outs": getattr(state, "outs", 0) or 0,
		"balls": getattr(state, "balls", 0) or 0,
		"strikes": getattr(state, "strikes", 0) or 0,
		"is_clutch": is_clutch,
		"is_late": is_late,
		"is_close": is_close,
		"pressure_state": pressure_state,
		"runners_on": [runner is not None for runner in runners],
		"is_risp": is_risp,
		"bases_loaded": bases_loaded,
		"batter_hand": (batter_hand or "R").upper()[0],
		"pitcher_hand": (pitcher_hand or "R").upper()[0],
		"lineup_slot": lineup_slot,
		"pitch_count": pitch_count,
		"momentum": getattr(state, "momentum", 0),
		"batter_team_id": batter_team_id,
		"pitcher_team_id": pitcher_team_id,
		"offense_team_id": offense_team_id,
		"defense_team_id": defense_team_id,
		"is_home_game": batter_team_id == getattr(state.home_team, "id", None),
		"runners_detail": [getattr(runner, "id", None) if runner else None for runner in runners],
	}

	risp_count = sum(1 for runner in runners[1:] if runner is not None)
	context["risp_count"] = risp_count
	context["is_trailing"] = score_diff < 0
	context["score_tied"] = score_diff == 0

	return context


__all__ = ["get_at_bat_context"]