# match_engine/manager_ai.py
from typing import Optional

from sqlalchemy.orm import Session

from database.setup_db import Player
from .commentary import commentary_enabled
from .fatigue_injury import check_pitcher_injury_risk


def _player_has_milestone(state, player_id, milestone_key: str) -> bool:
    checker = getattr(state, "player_has_milestone", None)
    if callable(checker):
        return checker(player_id, milestone_key)
    milestones = getattr(state, 'player_milestones', {}) or {}
    entries = milestones.get(player_id, [])
    target = milestone_key.lower()
    return any((entry.get("key") or "").lower() == target for entry in entries)


def _bench_for_team(state, team_id):
    bench_map = getattr(state, 'bench_players', {}) or {}
    bench = bench_map.get(team_id)
    if bench is None:
        bench_map[team_id] = []
        bench = bench_map[team_id]
    return bench


def _remove_from_bench(state, team_id, player_id):
    bench = _bench_for_team(state, team_id)
    bench[:] = [p for p in bench if getattr(p, 'id', None) != player_id]


def _pop_shutdown_specialist(state, team_id) -> Optional[Player]:
    bench = _bench_for_team(state, team_id)
    specialists = [
        p for p in bench
        if getattr(p, 'position', '').lower() == 'pitcher'
        and _player_has_milestone(state, getattr(p, 'id', None), 'shutdown_specialist')
    ]
    if not specialists:
        return None

    def _score(pitcher: Player):
        return (pitcher.control or 0) * 1.2 + (pitcher.stamina or 0)

    choice = max(specialists, key=_score)
    _remove_from_bench(state, team_id, getattr(choice, 'id', None))
    return choice


def find_relief_pitcher(state, team_id, current_pitcher_id):
    """Find a fresh pitcher for the given team."""
    db_session: Session = state.db_session
    pitchers = db_session.query(Player).filter_by(school_id=team_id, position='Pitcher').all()
    available = [p for p in pitchers if p.id != current_pitcher_id and p.injury_days == 0]
    if not available:
        return None

    def _score(pitcher: Player):
        base = (pitcher.velocity or 0) + (pitcher.control or 0) + (pitcher.stamina or 0)
        if _player_has_milestone(state, pitcher.id, "shutdown_specialist"):
            base += 45
        elif _player_has_milestone(state, pitcher.id, "ironman_workhorse"):
            base += 25
        return base

    return max(available, key=_score)


def _team_mod_types(state, team_id):
    mods = getattr(state, 'team_mods', None) or {}
    return {m['type'] for m in mods.get(team_id, [])}


def _score_margin(state, team_side):
    diff = state.home_score - state.away_score
    return diff if team_side == 'Home' else -diff


def _maybe_script_shutdown_specialist(state, team_side, team, current_pitcher):
    inning = getattr(state, 'inning', 1)
    if inning < 7 or state.outs != 0:
        return False
    margin = _score_margin(state, team_side)
    if margin <= 0 or margin > 3:
        return False
    if _player_has_milestone(state, getattr(current_pitcher, 'id', None), 'shutdown_specialist'):
        return False
    specialist = _pop_shutdown_specialist(state, team.id)
    if not specialist:
        return False
    perform_pitching_change(state, team_side, specialist, reason="shutdown-script")
    if commentary_enabled():
        name = getattr(specialist, 'last_name', getattr(specialist, 'name', 'Pitcher'))
        print(f"   🧊 Shutdown Specialist enters to protect the lead ({name}).")
    return True


def manage_team_between_innings(state, team_side):
    """Checks if the manager should change pitchers between innings."""
    team = state.home_team if team_side == 'Home' else state.away_team
    pitcher = state.home_pitcher if team_side == 'Home' else state.away_pitcher
    if not pitcher:
        return

    if _maybe_script_shutdown_specialist(state, team_side, team, pitcher):
        return

    p_count = state.pitch_counts.get(pitcher.id, 0)
    is_injured, severity = check_pitcher_injury_risk(pitcher, state, state.db_session)
    if is_injured:
        if commentary_enabled():
            print(f"   🚑 MANAGER ALERT: {pitcher.last_name} is injured ({severity}) and must be pulled.")
        new_pitcher = find_relief_pitcher(state, team.id, pitcher.id)
        if new_pitcher:
            perform_pitching_change(state, team_side, new_pitcher, reason="injury")
        else:
            if commentary_enabled():
                print(f"   ⚠️ No relief pitchers available! {pitcher.last_name} must soldier on.")
        return

    stamina = getattr(pitcher, 'stamina', 50)
    limit = stamina + 40
    mod_types = _team_mod_types(state, team.id)
    if 'small_ball' in mod_types:
        limit -= 10
        if commentary_enabled():
            print("   📋 Coach directive: Quick hook for pitchers (Small Ball focus).")
    if 'power_focus' in mod_types:
        limit += 10
        if commentary_enabled():
            print("   🔥 Coach directive: Let pitchers battle longer (Swing Free).")
    if _player_has_milestone(state, getattr(pitcher, 'id', None), "shutdown_specialist"):
        limit += 12
    elif _player_has_milestone(state, getattr(pitcher, 'id', None), "ironman_workhorse"):
        limit += 8

    if p_count > limit:
        if commentary_enabled():
            print(f"   👀 MANAGER: {pitcher.last_name} looks tired (Count: {p_count}). Warming up bullpen...")
        new_pitcher = find_relief_pitcher(state, team.id, pitcher.id)
        if new_pitcher:
            perform_pitching_change(state, team_side, new_pitcher, reason="fatigue")


def _register_pitcher_usage(state, team_side, new_pitcher, old_pitcher):
    team_id = state.home_team.id if team_side == 'Home' else state.away_team.id
    _remove_from_bench(state, team_id, getattr(new_pitcher, 'id', None))
    state.player_team_map[new_pitcher.id] = team_id
    state.player_lookup[new_pitcher.id] = new_pitcher
    history = getattr(state, 'pitching_changes', None)
    if history is None:
        state.pitching_changes = []
        history = state.pitching_changes
    history.append({
        "team_id": team_id,
        "old_pitcher": getattr(old_pitcher, 'id', None) if old_pitcher else None,
        "new_pitcher": getattr(new_pitcher, 'id', None),
        "inning": getattr(state, 'inning', 0),
        "reason": state.last_change_reason,
    })


def perform_pitching_change(state, team_side, new_pitcher, reason="strategy"):
    old_pitcher = state.home_pitcher if team_side == 'Home' else state.away_pitcher
    if old_pitcher and getattr(old_pitcher, 'id', None) == getattr(new_pitcher, 'id', None):
        return
    state.last_change_reason = reason
    if team_side == 'Home':
        if commentary_enabled():
            print(f"   🔄 PITCHING CHANGE (Home): {getattr(old_pitcher, 'last_name', '??')} -> {new_pitcher.last_name}")
        state.home_pitcher = new_pitcher
    else:
        if commentary_enabled():
            print(f"   🔄 PITCHING CHANGE (Away): {getattr(old_pitcher, 'last_name', '??')} -> {new_pitcher.last_name}")
        state.away_pitcher = new_pitcher
    state.pitch_counts.setdefault(getattr(new_pitcher, 'id', None), 0)
    _register_pitcher_usage(state, team_side, new_pitcher, old_pitcher)