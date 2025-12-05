from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple
from battery_system.battery_trust import adjust_confidence_delta_for_battery
from game.skill_system import player_has_skill
from match_engine.telemetry import capture_confidence_swing

CONFIDENCE_MIN = -100
CONFIDENCE_MAX = 100


def _clamp(value: float) -> int:
    return int(max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, round(value))))


def _base_confidence(player) -> int:
    drive = getattr(player, "drive", 50) or 50
    loyalty = getattr(player, "loyalty", 50) or 50
    volatility = getattr(player, "volatility", 50) or 50
    morale = getattr(player, "morale", 60) or 60
    slump = getattr(player, "slump_timer", 0) or 0
    base = (drive - 50) * 1.4
    base += (morale - 60) * 0.4
    base += (loyalty - 50) * 0.2
    base -= (volatility - 50) * 0.8
    base -= slump * 1.5
    return _clamp(base)


def _team_roster(state, team_id: int) -> List:
    return (getattr(state, "team_rosters", {}) or {}).get(team_id, [])


def _player_lookup(state, player_id: int):
    lookup = getattr(state, "player_lookup", {}) or {}
    return lookup.get(player_id)


def initialize_confidence(state) -> None:
    state.confidence_map = {}
    player_team_map: Dict[int, int] = {}
    lookup = getattr(state, "player_lookup", {})

    for team_id, roster in (getattr(state, "team_rosters", {}) or {}).items():
        for player in roster:
            if not player:
                continue
            player_team_map[player.id] = team_id
            if player.id not in state.confidence_map:
                state.confidence_map[player.id] = _base_confidence(player)
    for pitcher, team_id in (
        (getattr(state, "home_pitcher", None), getattr(state.home_team, "id", None)),
        (getattr(state, "away_pitcher", None), getattr(state.away_team, "id", None)),
    ):
        if not pitcher or team_id is None:
            continue
        player_team_map[pitcher.id] = team_id
        lookup.setdefault(pitcher.id, pitcher)
        state.confidence_map.setdefault(pitcher.id, _base_confidence(pitcher))

    state.player_team_map = player_team_map
    _sync_loyalty_bias(state)
    _sync_battery_pairs(state)
    _apply_home_field_advantage(state)


def _sync_loyalty_bias(state) -> None:
    for team_id, roster in (getattr(state, "team_rosters", {}) or {}).items():
        if not roster:
            continue
        captain = next((p for p in roster if getattr(p, "is_captain", False)), None)
        if not captain:
            continue
        cap_conf = state.confidence_map.get(captain.id, 0)
        for player in roster:
            if player.id == captain.id:
                continue
            loyalty = getattr(player, "loyalty", 50) or 50
            if loyalty >= 75:
                _nudge_toward(state, player.id, cap_conf, 0.25)


def _sync_battery_pairs(state) -> None:
    for team_id, roster in (getattr(state, "team_rosters", {}) or {}).items():
        catcher = next((p for p in roster if (p.position or "").lower() == "catcher"), None)
        pitcher = None
        for active_pitcher in (getattr(state, "home_pitcher", None), getattr(state, "away_pitcher", None)):
            if not active_pitcher:
                continue
            pid = getattr(active_pitcher, "id", None)
            if pid and state.player_team_map.get(pid) == team_id:
                pitcher = active_pitcher
                break
        if pitcher and catcher:
            avg = (state.confidence_map.get(pitcher.id, 0) + state.confidence_map.get(catcher.id, 0)) / 2
            _nudge_toward(state, pitcher.id, avg, 0.2)
            _nudge_toward(state, catcher.id, avg, 0.2)


def _nudge_toward(state, player_id: int, target: float, ratio: float) -> None:
    current = get_confidence(state, player_id)
    new_value = current + (target - current) * ratio
    state.confidence_map[player_id] = _clamp(new_value)


def get_confidence(state, player_id: int, default: int = 0) -> int:
    return (getattr(state, "confidence_map", {}) or {}).get(player_id, default)


def adjust_confidence(state, player_id: int, delta: float, *, reason: Optional[str] = None, contagious: bool = True) -> int:
    if not player_id:
        return 0
    confidence_map = getattr(state, "confidence_map", None)
    if confidence_map is None:
        return 0
    player = _player_lookup(state, player_id)
    base_delta = float(delta)
    if not player:
        return 0
    has_mental_wall = player_has_skill(player, "mental_wall")
    has_control_freak = player_has_skill(player, "control_freak")

    if base_delta < 0 and reason in {"error", "wild_pitch", "strikeout"}:
        volatility = getattr(player, "volatility", 50) or 50
        if has_control_freak:
            volatility = min(volatility, 55)
        base_delta *= 1 + max(0, (volatility - 55) / 90)
    elif base_delta > 0 and reason in {"clutch_hit", "heroics", "shutout", "discipline"}:
        drive = getattr(player, "drive", 50) or 50
        base_delta *= 1 + max(0, (drive - 60) / 120)
    if base_delta < 0 and reason in {"error", "wild_pitch", "strikeout", "hit_allowed", "out"}:
        resilience = getattr(player, "mental", getattr(player, "discipline", 50)) or 50
        if resilience < 45:
            base_delta -= 4
        elif resilience >= 70:
            base_delta *= 0.5
    if base_delta < 0 and has_mental_wall:
        base_delta *= 0.5

    previous = confidence_map.get(player_id, 0)
    base_delta = _apply_battery_cushion(state, player_id, base_delta)
    new_value = _clamp(previous + base_delta)
    confidence_map[player_id] = new_value
    actual_delta = new_value - previous
    if actual_delta:
        _record_confidence_story(state, player_id, actual_delta, reason)
        _queue_confidence_event(state, player_id, actual_delta, reason)
        capture_confidence_swing(state, player_id, actual_delta, reason=reason)

    if contagious and actual_delta != 0:
        _propagate(state, player_id, actual_delta, reason)
    return confidence_map[player_id]


def _propagate(state, player_id: int, delta: float, reason: Optional[str]) -> None:
    team_id = state.player_team_map.get(player_id) if hasattr(state, "player_team_map") else None
    if team_id is None:
        return
    teammates = [p for p in _team_roster(state, team_id) if p and p.id != player_id]
    if not teammates:
        return

    if delta > 0:
        # High loyalty teammates soak up the confidence surge
        for mate in teammates:
            loyalty = getattr(mate, "loyalty", 50) or 50
            if loyalty >= 72:
                _nudge_toward(state, mate.id, get_confidence(state, player_id), 0.18)
    else:
        # Negative swings rattle volatile teammates
        for mate in teammates:
            volatility = getattr(mate, "volatility", 50) or 50
            if volatility >= 65:
                confidence = get_confidence(state, mate.id)
                confidence = _clamp(confidence + delta * 0.2)
                state.confidence_map[mate.id] = confidence


def _apply_home_field_advantage(state) -> None:
    home_team = getattr(state, "home_team", None)
    away_team = getattr(state, "away_team", None)
    rosters = (getattr(state, "team_rosters", {}) or {})
    if not home_team or not away_team:
        return
    home_roster = rosters.get(getattr(home_team, "id", None), [])
    away_roster = rosters.get(getattr(away_team, "id", None), [])
    if home_roster:
        for player in home_roster:
            if not player or not getattr(player, "id", None):
                continue
            bonus = 2
            if getattr(player, "is_captain", False):
                bonus += 1
            adjust_confidence(state, player.id, bonus, reason="home_field", contagious=False)
    if away_roster:
        for player in away_roster:
            if not player or not getattr(player, "id", None):
                continue
            adjust_confidence(state, player.id, -1, reason="road_game", contagious=False)


def apply_fielding_error_confidence(state, team_id: int, primary_position: Optional[str]) -> None:
    roster = _team_roster(state, team_id)
    if not roster:
        return
    target = _player_by_position(roster, primary_position)
    if not target:
        target = roster[0]
    adjust_confidence(state, target.id, -18, reason="error", contagious=False)
    for adj in _adjacent_positions(primary_position):
        ally = _player_by_position(roster, adj)
        if ally and ally.id != target.id:
            adjust_confidence(state, ally.id, -7, reason="error", contagious=False)


def _player_by_position(roster: Iterable, position: Optional[str]):
    if not position:
        return None
    position = position.lower()
    for player in roster:
        player_pos = (getattr(player, "position", "") or "").lower()
        if player_pos == position:
            return player
    return None


def _adjacent_positions(position: Optional[str]) -> List[str]:
    if not position:
        return []
    position = position.upper()
    mapping = {
        "PITCHER": ["CATCHER"],
        "CATCHER": ["PITCHER", "FIRST BASE"],
        "FIRST BASE": ["SECOND BASE", "CATCHER"],
        "SECOND BASE": ["SHORTSTOP", "FIRST BASE"],
        "SHORTSTOP": ["SECOND BASE", "THIRD BASE"],
        "THIRD BASE": ["SHORTSTOP", "LEFT FIELD"],
        "LEFT FIELD": ["CENTER FIELD", "THIRD BASE"],
        "CENTER FIELD": ["LEFT FIELD", "RIGHT FIELD"],
        "RIGHT FIELD": ["CENTER FIELD"],
    }
    return mapping.get(position, [])


def _player_label(player) -> str:
    if not player:
        return "Player"
    return getattr(player, "last_name", None) or getattr(player, "name", None) or getattr(player, "first_name", None) or "Player"


def _record_confidence_story(state, player_id: int, delta: float, reason: Optional[str]) -> None:
    story = getattr(state, "confidence_story", None)
    if story is None:
        return
    entry = story.setdefault(player_id, {
        "max_gain": 0,
        "max_drop": 0,
        "events": [],
    })
    if delta > entry["max_gain"]:
        entry["max_gain"] = delta
    if delta < entry["max_drop"]:
        entry["max_drop"] = delta
    events = entry["events"]
    if len(events) >= 10:
        events.pop(0)
    events.append({
        "delta": delta,
        "reason": reason,
        "inning": getattr(state, "inning", 0),
    })


def _queue_confidence_event(state, player_id: int, delta: float, reason: Optional[str]) -> None:
    if abs(delta) < 5:
        return
    queue = getattr(state, "confidence_events", None)
    if queue is None:
        return
    player = _player_lookup(state, player_id)
    queue.append({
        "player_id": player_id,
        "name": _player_label(player),
        "team_id": getattr(player, "team_id", getattr(player, "school_id", None)) if player else None,
        "delta": delta,
        "reason": reason,
        "inning": getattr(state, "inning", 0),
        "announced": False,
    })


def collect_confidence_flashes(state) -> List[dict]:
    queue = getattr(state, "confidence_events", None)
    if not queue:
        return []
    flashes = []
    for event in queue:
        if event.get("announced"):
            continue
        event["announced"] = True
        flashes.append(event)
    return flashes


def get_confidence_trends(state) -> Optional[dict]:
    story = getattr(state, "confidence_story", None)
    if not story:
        return None
    rising: Tuple[int, float] | None = None
    falling: Tuple[int, float] | None = None
    for pid, info in story.items():
        gain = info.get("max_gain", 0)
        drop = info.get("max_drop", 0)
        if gain and (not rising or gain > rising[1]):
            rising = (pid, gain)
        if drop and (not falling or drop < falling[1]):
            falling = (pid, drop)
    if not rising and not falling:
        return None
    lookup = getattr(state, "player_lookup", {})
    def describe(entry):
        if not entry:
            return None
        pid, value = entry
        player = lookup.get(pid)
        return {
            "player_id": pid,
            "name": _player_label(player),
            "value": value,
        }
    return {
        "rising": describe(rising),
        "falling": describe(falling),
    }


def get_confidence_summary(state):
    return getattr(state, "confidence_story", {})


def _defense_team_id(state) -> Optional[int]:
    if getattr(state, "top_bottom", "Top") == "Top":
        return getattr(state.home_team, "id", None)
    return getattr(state.away_team, "id", None)


def _offense_team_id(state) -> Optional[int]:
    if getattr(state, "top_bottom", "Top") == "Top":
        return getattr(state.away_team, "id", None)
    return getattr(state.home_team, "id", None)


def _team_catcher(state, team_id: Optional[int]):
    if team_id is None:
        return None

    roster = _team_roster(state, team_id)
    for player in roster:
        if (getattr(player, "position", "") or "").lower() == "catcher":
            return player
    return None


def _active_pitcher_pair(state, player_id: int):
    home_pitcher = getattr(state, "home_pitcher", None)
    away_pitcher = getattr(state, "away_pitcher", None)
    if home_pitcher and getattr(home_pitcher, "id", None) == player_id:
        return home_pitcher, _team_catcher(state, getattr(state.home_team, "id", None))
    if away_pitcher and getattr(away_pitcher, "id", None) == player_id:
        return away_pitcher, _team_catcher(state, getattr(state.away_team, "id", None))
    return None, None


def _apply_battery_cushion(state, player_id: int, delta: float) -> float:
    if delta == 0:
        return 0.0
    if not hasattr(state, "home_pitcher"):
        return delta
    pitcher, catcher = _active_pitcher_pair(state, player_id)
    if not pitcher or not catcher:
        return delta
    return adjust_confidence_delta_for_battery(pitcher, catcher, delta)

def record_pitcher_stress(state, pitcher_id: Optional[int], spike: bool = True) -> None:
    tracker = getattr(state, "pitcher_stress", None)
    if tracker is None or not pitcher_id:
        return
    if spike:
        tracker[pitcher_id] = tracker.get(pitcher_id, 0) + 1
        if tracker[pitcher_id] >= 2:
            maybe_catcher_settle(state, pitcher_id, force=True)
    else:
        tracker[pitcher_id] = 0


def maybe_catcher_settle(state, pitcher_id: Optional[int], *, force: bool = False) -> bool:
    if not pitcher_id:
        return False
    team_id = _defense_team_id(state)
    catcher = _team_catcher(state, team_id)
    if not catcher:
        return False
    loyalty = getattr(catcher, "loyalty", 50) or 50
    volatility = getattr(catcher, "volatility", 50) or 50
    if loyalty < 65 or volatility > 55:
        return False
    tracker = getattr(state, "catcher_settle_log", None)
    if tracker is None:
        return False
    log = tracker.setdefault(pitcher_id, {"uses": 0, "last_inning": 0})
    if log["uses"] >= 3 or log["last_inning"] == getattr(state, "inning", 0):
        return False
    current_conf = get_confidence(state, pitcher_id)
    if not force and current_conf > -25:
        return False
    adjust_confidence(state, pitcher_id, 6, reason="catcher_settle", contagious=False)
    adjust_confidence(state, getattr(catcher, "id", None), -2, reason="catcher_settle", contagious=False)
    log["uses"] += 1
    log["last_inning"] = getattr(state, "inning", 0)
    if hasattr(state, "pitcher_stress"):
        state.pitcher_stress[pitcher_id] = 0
    return True


def record_rally_progress(state, team_id: Optional[int], batter_id: Optional[int], *, reached_base: bool) -> None:
    tracker = getattr(state, "rally_tracker", None)
    if tracker is None or team_id is None:
        return
    data = tracker.setdefault(team_id, {"streak": 0, "participants": [], "hot": False})
    if reached_base:
        data["streak"] += 1
        if batter_id:
            data["participants"].append(batter_id)
            data["participants"] = data["participants"][-5:]
        if data["streak"] >= 3 and not data["hot"]:
            _apply_rally_bonus(state, team_id, data["participants"])
            data["hot"] = True
    else:
        data["streak"] = 0
        data["participants"] = []
        data["hot"] = False


def reset_rally_tracker(state, team_id: Optional[int]) -> None:
    tracker = getattr(state, "rally_tracker", None)
    if tracker is None or team_id is None:
        return
    tracker[team_id] = {"streak": 0, "participants": [], "hot": False}


def _apply_rally_bonus(state, team_id: int, participants: Iterable[int]) -> None:
    for pid in set(participants):
        adjust_confidence(state, pid, 4, reason="rally")
    roster = _team_roster(state, team_id)
    for runner in getattr(state, "runners", []):
        if not runner or state.player_team_map.get(getattr(runner, "id", None)) != team_id:
            continue
        loyalty = getattr(runner, "loyalty", 50) or 50
        if loyalty >= 70:
            adjust_confidence(state, getattr(runner, "id", None), 2, reason="rally")
    captain = next((p for p in roster if getattr(p, "is_captain", False)), None)
    if captain:
        adjust_confidence(state, getattr(captain, "id", None), 2, reason="captain_surge", contagious=False)


def apply_lead_change_swing(state) -> None:
    offense_id = _offense_team_id(state)
    defense_id = _defense_team_id(state)
    if offense_id is None or defense_id is None:
        return
    offense_roster = _team_roster(state, offense_id)
    defense_roster = _team_roster(state, defense_id)
    for player in offense_roster:
        if not player:
            continue
        loyalty = getattr(player, "loyalty", 50) or 50
        boost = 5 if loyalty >= 70 else 3
        adjust_confidence(state, getattr(player, "id", None), boost, reason="rally")
    for player in defense_roster:
        if not player:
            continue
        volatility = getattr(player, "volatility", 50) or 50
        if volatility >= 65:
            adjust_confidence(state, getattr(player, "id", None), -4, reason="rally")


def apply_slump_boost(state, player_id: Optional[int], was_slumping: bool, event_type: str) -> None:
    if not was_slumping or not player_id:
        return
    tracker = getattr(state, "slump_boost", None)
    if tracker is None:
        return
    record = tracker.setdefault(player_id, {"chain": 0, "surge": False})
    if record.get("surge"):
        return
    if event_type not in {"hit", "walk", "rbi"}:
        return
    record["chain"] += 1
    adjust_confidence(state, player_id, 5, reason="slump_break", contagious=False)
    if record["chain"] >= 2 and not record["surge"]:
        adjust_confidence(state, player_id, 8, reason="slump_break", contagious=False)
        record["surge"] = True


def reset_slump_chain(state, player_id: Optional[int]) -> None:
    if not player_id:
        return
    tracker = getattr(state, "slump_boost", None)
    if tracker is None:
        return
    record = tracker.setdefault(player_id, {"chain": 0, "surge": False})
    record["chain"] = 0
