"""Helpers for assembling shared match and at-bat context dictionaries."""
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


def _player_position(player) -> Optional[str]:
	if not player:
		return None
	return getattr(player, "position", getattr(player, "primary_position", None))


def _player_role(player) -> Optional[str]:
	if not player:
		return None
	return getattr(player, "role", getattr(player, "player_role", getattr(player, "pitcher_role", None)))


def _lookup_counter(state, attr_name: str, player_id: Optional[int]) -> int:
	if not state or not player_id:
		return 0
	payload = getattr(state, attr_name, None)
	if isinstance(payload, dict):
		try:
			return int(payload.get(player_id, 0) or 0)
		except (TypeError, ValueError):
			return 0
	return 0


def get_at_bat_context(state, batter, pitcher) -> Dict[str, object]:
	"""Return a normalized dictionary summarizing the current plate appearance."""
	inning = getattr(state, "inning", 1) or 1
	top_half = getattr(state, "top_bottom", "Top") == "Top"
	offense_team_id = getattr(state.away_team, "id", None) if top_half else getattr(state.home_team, "id", None)
	defense_team_id = getattr(state.home_team, "id", None) if top_half else getattr(state.away_team, "id", None)
	batter_team_id = _player_team_id(batter)
	pitcher_team_id = _player_team_id(pitcher)
	batter_id = getattr(batter, "id", None)
	pitcher_id = getattr(pitcher, "id", None)
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
	batter_position = _player_position(batter)
	batter_role = _player_role(batter)
	pitcher_role = _player_role(pitcher)
	is_relief_pitcher = str(pitcher_role or "").upper() in {"RELIEVER", "CLOSER"}
	is_ace_start = str(pitcher_role or "").upper() == "ACE"
	is_spot_start = bool(getattr(pitcher, "spot_start", False) or str(getattr(pitcher, "assignment", "")).lower() == "spot")
	is_pinch = bool(getattr(batter, "_pinch_flag", False))
	balls = getattr(state, "balls", 0) or 0
	strikes = getattr(state, "strikes", 0) or 0

	pressure_state = "high" if (is_clutch or is_risp) else "normal"

	context: Dict[str, object] = {
		"inning": inning,
		"top_half": top_half,
		"score_diff": score_diff,
		"offense_score": offense_score,
		"defense_score": defense_score,
		"outs": getattr(state, "outs", 0) or 0,
		"balls": balls,
		"strikes": strikes,
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
		"player_position": batter_position,
		"player_role": batter_role,
		"pitcher_role": pitcher_role,
		"is_relief_pitcher": is_relief_pitcher,
		"is_spot_start": is_spot_start,
		"is_ace_start": is_ace_start,
		"is_pinch_hitting": is_pinch,
	}

	risp_count = sum(1 for runner in runners[1:] if runner is not None)
	context["risp_count"] = risp_count
	context["is_trailing"] = score_diff < 0
	context["score_tied"] = score_diff == 0
	context["defense_trailing"] = score_diff > 0
	context["is_two_strike"] = strikes >= 2
	context["is_full_count"] = balls == 3 and strikes == 2
	context["is_cleanup_spot"] = lineup_slot == 4
	context["is_leadoff_spot"] = lineup_slot == 1
	context["is_postseason"] = bool(getattr(state, "is_postseason", False) or getattr(state, "tournament_mode", False))
	context["game_importance"] = getattr(state, "game_importance", "regular")
	context["is_season_opener"] = bool(getattr(state, "is_season_opener", False))
	context["crowd_factor"] = getattr(state, "crowd_factor", 0)
	context["is_hostile_env"] = bool(getattr(state, "hostile_env", False) or (not context["is_home_game"] and context["crowd_factor"] < 0))
	context["has_scouting_edge"] = getattr(state, "scouting_edge_team_id", None) == offense_team_id
	context["routine_active"] = bool(getattr(state, "routine_active_ids", set()) and batter_id in getattr(state, "routine_active_ids", set())) or bool(getattr(batter, "_routine_active", False))
	context["hot_streak_length"] = max(
		_lookup_counter(state, "player_hot_streaks", batter_id),
		int(getattr(batter, "_hot_streak", 0) or 0),
	)
	context["is_hot_streak"] = context["hot_streak_length"] >= 3
	context["is_slumping"] = _lookup_counter(state, "slump_tracker", batter_id) >= max(3, getattr(state, "slump_threshold", 3))
	context["inherited_runners"] = bool(context["runners_on"] and any(context["runners_on"]) and pitch_count <= 5 and is_relief_pitcher)
	context["routine_active"] = context.get("routine_active")
	context["is_pinch_hitting"] = is_pinch
	context["is_spot_start"] = is_spot_start
	context["is_ace_start"] = is_ace_start
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["is_hostile_env"] = context.get("is_hostile_env")
	context["is_postseason"] = context.get("is_postseason")
	context["is_season_opener"] = context.get("is_season_opener")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["is_hot_streak"] = context.get("is_hot_streak")
	context["routine_active"] = context.get("routine_active")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")
	context["has_scouting_edge"] = context.get("has_scouting_edge")

	return context


__all__ = ["get_at_bat_context"]