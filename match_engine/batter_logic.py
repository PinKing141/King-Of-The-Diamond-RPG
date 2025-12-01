import time
from .pitch_logic import resolve_pitch, get_current_catcher
from .ball_in_play import resolve_contact
from .base_running import advance_runners, resolve_steal_attempt
from .commentary import (
    display_state,
    announce_pitch,
    announce_play,
    announce_score_change,
    commentary_enabled,
)
from game.rng import get_rng
from match_engine.confidence import (
    adjust_confidence,
    apply_fielding_error_confidence,
    apply_lead_change_swing,
    apply_slump_boost,
    collect_confidence_flashes,
    get_confidence,
    maybe_catcher_settle,
    record_pitcher_stress,
    record_rally_progress,
    reset_rally_tracker,
    reset_slump_chain,
)

rng = get_rng()


def _update_pitch_diagnostics(state, pitcher_id, outcome):
    tracker = state.pitcher_diagnostics.setdefault(
        pitcher_id,
        {"pitches": 0, "balls": 0, "last_comment_pitch": 0, "last_k_comment": 0},
    )
    tracker["pitches"] += 1
    if outcome == "Ball":
        tracker["balls"] += 1
    return tracker


def _maybe_comment_on_control(pitcher, tracker):
    if not commentary_enabled():
        return
    total = tracker.get("pitches", 0)
    if total < 12:
        return
    ball_ratio = tracker.get("balls", 0) / max(1, total)
    if ball_ratio < 0.45:
        return
    if total - tracker.get("last_comment_pitch", 0) < 8:
        return
    name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'The pitcher'))
    print(f"   >> {name} is struggling to find the zone right now.")
    tracker["last_comment_pitch"] = total


def _maybe_comment_on_dominance(pitcher, tracker, pitcher_stats):
    if not commentary_enabled():
        return
    strikeouts = int(pitcher_stats.get("strikeouts_pitched", 0))
    if strikeouts < 4 or strikeouts % 3 != 0:
        return
    if tracker.get("last_k_comment", 0) == strikeouts:
        return
    name = getattr(pitcher, 'last_name', getattr(pitcher, 'name', 'The pitcher'))
    print(f"   >> {name} already has {strikeouts} strikeouts. The hitters look lost.")
    tracker["last_k_comment"] = strikeouts


def _offense_context(state):
    if state.top_bottom == "Top":
        return state.away_team, state.home_pitcher
    return state.home_team, state.away_pitcher


def _player_team_id(player):
    return getattr(player, 'team_id', getattr(player, 'school_id', None))


def _maybe_call_aggressive_play(state):
    """High-volatility coaches occasionally send the runner."""
    offense_team, opp_pitcher = _offense_context(state)
    coach = getattr(offense_team, 'coach', None)
    if coach is None:
        return None

    runner = state.runners[0]
    if not runner or state.runners[1] is not None:
        return None
    # Skip manual/user-controlled teams (legacy assumption: team_id 1)
    if _player_team_id(runner) == 1:
        return None

    volatility = getattr(coach, 'volatility', 50) or 50
    drive = getattr(coach, 'drive', 50) or 50
    loyalty = getattr(coach, 'loyalty', 50) or 50

    base_chance = 0.03
    base_chance += max(0, volatility - 50) * 0.002
    base_chance += max(0, drive - 55) * 0.0015
    base_chance -= max(0, 55 - loyalty) * 0.001
    runner_speed = getattr(runner, 'speed', 50) or 50
    base_chance += max(0, runner_speed - 65) * 0.001

    # Late innings or when trailing nudges aggression upward
    offense_is_away = state.top_bottom == "Top"
    score_diff = (state.away_score - state.home_score) if offense_is_away else (state.home_score - state.away_score)
    if state.inning >= 7 and abs(score_diff) <= 2:
        base_chance += 0.02
    if score_diff < 0:
        base_chance += 0.01

    base_chance = max(0.0, min(0.35, base_chance))
    if rng.random() > base_chance:
        return None

    catcher = get_current_catcher(state)
    success, message = resolve_steal_attempt(runner, opp_pitcher, catcher, "2B")
    if commentary_enabled():
        coach_name = getattr(coach, 'name', 'Coach')
        runner_name = getattr(runner, 'last_name', getattr(runner, 'name', 'Runner'))
        print(f"   >> {coach_name} flashes the steal sign for {runner_name}!")
        print(f"   >> {message}")

    state.runners[0] = None
    if success:
        state.runners[1] = runner
        return "continue"

    state.outs += 1
    return "runner_out"


def _advance_on_wild_pitch(state):
    """Advance all runners one base on a wild pitch, return runs scored."""
    new_runners = [None, None, None]
    runs = 0
    for base in range(2, -1, -1):
        runner = state.runners[base]
        if not runner:
            continue
        dest = base + 1
        if dest >= 3:
            runs += 1
        else:
            new_runners[dest] = runner
    state.runners = new_runners
    return runs


def _defense_team_id(state):
    return state.home_team.id if state.top_bottom == "Top" else state.away_team.id


def _offense_team_id(state):
    return state.away_team.id if state.top_bottom == "Top" else state.home_team.id


def _lead_changed(state, runs_scored, pre_home, pre_away):
    if runs_scored <= 0:
        return False
    if state.top_bottom == "Top":
        before = pre_away - pre_home
        after = (pre_away + runs_scored) - pre_home
    else:
        before = pre_home - pre_away
        after = (pre_home + runs_scored) - pre_away
    return before <= 0 and after > 0


def _apply_walk_confidence(state, batter, pitcher):
    adjust_confidence(state, getattr(batter, 'id', None), 2, reason="discipline")
    adjust_confidence(state, getattr(pitcher, 'id', None), -2, reason="discipline")


def _apply_strikeout_confidence(state, batter, pitcher):
    adjust_confidence(state, getattr(batter, 'id', None), -8, reason="strikeout")
    adjust_confidence(state, getattr(pitcher, 'id', None), 4, reason="strikeout")


def _apply_contact_confidence(state, batter, pitcher, contact_res):
    if contact_res.error_on_play:
        apply_fielding_error_confidence(state, _defense_team_id(state), contact_res.primary_position)
    if contact_res.hit_type == "Out":
        adjust_confidence(state, getattr(batter, 'id', None), -4, reason="out")
        adjust_confidence(state, getattr(pitcher, 'id', None), 3, reason="heroics")
        return
    boosts = {"1B": 5, "2B": 7, "3B": 9, "HR": 12}
    base = boosts.get(contact_res.hit_type, 4)
    if not contact_res.credited_hit:
        base = max(2, base - 3)
    adjust_confidence(state, getattr(batter, 'id', None), base, reason="clutch_hit")
    adjust_confidence(state, getattr(pitcher, 'id', None), -min(base, 8), reason="hit_allowed")


def _broadcast_confidence_flashes(state):
    if not commentary_enabled():
        collect_confidence_flashes(state)
        return
    for event in collect_confidence_flashes(state):
        direction = "surging" if event["delta"] > 0 else "reeling"
        magnitude = f"{event['delta']:+.0f}"
        reason = event.get("reason") or "moment"
        inning = event.get("inning") or getattr(state, "inning", 0)
        print(f"   >> Confidence pulse ({inning}): {event['name']} is {direction} ({magnitude}, {reason}).")


def _handle_argument_event(state, pitch_res, batter, pitcher):
    label = getattr(pitch_res, 'special', None)
    if label not in {"argument_batter", "argument_pitcher"}:
        return
    penalty = getattr(pitch_res, 'argument_penalty', 0) or 0
    if penalty <= 0:
        return
    target = batter if label == "argument_batter" else pitcher
    target_id = getattr(target, 'id', None)
    adjust_confidence(state, target_id, -penalty, reason="ump_argument", contagious=False)
    morale = getattr(target, 'morale', 60) or 60
    morale -= max(1, penalty // 2)
    target.morale = max(15, morale)
    if commentary_enabled():
        name = getattr(target, 'last_name', getattr(target, 'name', 'Player'))
        print(f"   >> {name} barks at the ump and gets rattled ({penalty} confidence hit).")

def start_at_bat(state):
    """
    Simulates one complete At-Bat.
    Returns True if the inning continues, False if 3 outs reached immediately.
    """
    pitcher = state.home_pitcher if state.top_bottom == "Top" else state.away_pitcher
    batter = state.away_lineup[0] if state.top_bottom == "Top" else state.home_lineup[0]
    batting_team = state.away_team if state.top_bottom == "Top" else state.home_team
    offense_team_id = _offense_team_id(state)
    batter_id = getattr(batter, 'id', None)
    pitcher_id = getattr(pitcher, 'id', None)
    
    state.reset_count()
    batter_stats = state.get_stats(batter.id)
    pitcher_stats = state.get_stats(pitcher.id)
    if commentary_enabled():
        display_state(state, pitcher, batter)
    
    steal_checked = False
    while True:
        # time.sleep(0.5) # Pace the game
        
        # --- USER INPUT CHECK (BATTER) ---
        batter_action = "Normal"
        batter_mods = {}
        
        # Check if Batter is USER (Assuming Team ID 1 is User)
        if _player_team_id(batter) == 1:
             from player_roles.batter_controls import player_bat_turn
             batter_action, batter_mods = player_bat_turn(pitcher, batter, state)
        
        if not steal_checked:
            steal_result = _maybe_call_aggressive_play(state)
            steal_checked = True
            if steal_result == "runner_out":
                if state.outs >= 3:
                    return
                continue

        # 1. Pitch Resolution (Pass batter intent)
        state.add_pitch_count(pitcher.id)
        pitch_res = resolve_pitch(pitcher, batter, state, batter_action, batter_mods)
        tracker = _update_pitch_diagnostics(state, pitcher.id, pitch_res.outcome)

        announce_pitch(pitch_res)
        _maybe_comment_on_control(pitcher, tracker)
        _handle_argument_event(state, pitch_res, batter, pitcher)
        
        # 2. Update Count
        if pitch_res.outcome == "Ball":
            state.balls += 1
            if getattr(pitch_res, 'special', None) == "wild_pitch":
                if commentary_enabled():
                    print("   >> Wild pitch! Everyone moves up 90 feet.")
                wild_runs = _advance_on_wild_pitch(state)
                if wild_runs:
                    announce_score_change(wild_runs, getattr(batting_team, 'name', 'Unknown School'))
                    if state.top_bottom == "Top":
                        state.away_score += wild_runs
                    else:
                        state.home_score += wild_runs
                    pitcher_stats["runs_allowed"] += wild_runs
                adjust_confidence(state, getattr(pitcher, 'id', None), -6, reason="wild_pitch")
                catcher = get_current_catcher(state)
                if catcher:
                    adjust_confidence(state, getattr(catcher, 'id', None), -3, reason="wild_pitch", contagious=False)
                record_pitcher_stress(state, pitcher_id, spike=True)
                maybe_catcher_settle(state, pitcher_id)
                if state.balls == 4:
                    if commentary_enabled():
                        print("   >> WALK.")
                    was_slumping = get_confidence(state, batter_id) <= -30
                    state.runners[0] = batter 
                    batter_stats["walks"] += 1
                    pitcher_stats["walks"] += 1
                    _apply_walk_confidence(state, batter, pitcher)
                    record_pitcher_stress(state, pitcher_id, spike=True)
                    record_rally_progress(state, offense_team_id, batter_id, reached_base=True)
                    apply_slump_boost(state, batter_id, was_slumping, "walk")
                    maybe_catcher_settle(state, pitcher_id)
                break
                
        elif pitch_res.outcome == "Strike":
            if state.strikes < 2 or pitch_res.description != "Foul": 
                state.strikes += 1
            
            if state.strikes == 3:
                if commentary_enabled():
                    print("   >> STRIKEOUT!")
                state.outs += 1
                batter_stats["strikeouts"] += 1
                pitcher_stats["strikeouts_pitched"] += 1
                _maybe_comment_on_dominance(pitcher, tracker, pitcher_stats)
                _apply_strikeout_confidence(state, batter, pitcher)
                reset_slump_chain(state, batter_id)
                record_pitcher_stress(state, pitcher_id, spike=False)
                reset_rally_tracker(state, offense_team_id)
                break
                
        elif pitch_res.outcome == "Foul":
            if state.strikes < 2:
                state.strikes += 1
                
        elif pitch_res.outcome == "InPlay":
            # 3. Contact
            p_mod = getattr(pitch_res, 'power_mod', 0)
            contact_res = resolve_contact(
                pitch_res.contact_quality,
                batter,
                pitcher,
                state,
                power_mod=p_mod,
            )
            announce_play(contact_res)
            reached_base = contact_res.hit_type != "Out"
            was_slumping = reached_base and get_confidence(state, batter_id) <= -30
            _apply_contact_confidence(state, batter, pitcher, contact_res)

            if contact_res.hit_type == "Out":
                state.outs += 1
                batter_stats["at_bats"] += 1
                pitcher_stats["innings_pitched"] += 0.33
                reset_slump_chain(state, batter_id)
                record_pitcher_stress(state, pitcher_id, spike=False)
                reset_rally_tracker(state, offense_team_id)
            else:
                batter_stats["at_bats"] += 1
                if contact_res.credited_hit:
                    batter_stats["hits"] += 1
                if contact_res.hit_type == "HR" and contact_res.credited_hit:
                    batter_stats["homeruns"] += 1

                pre_home = state.home_score
                pre_away = state.away_score
                runs = advance_runners(state, contact_res.hit_type, batter)
                lead_change = _lead_changed(state, runs, pre_home, pre_away)

                if runs > 0:
                    announce_score_change(runs, getattr(batting_team, 'name', 'Unknown School'))
                    if state.top_bottom == "Top":
                        state.away_score += runs
                    else:
                        state.home_score += runs

                    if contact_res.credited_hit:
                        batter_stats["rbi"] += runs
                    pitcher_stats["runs_allowed"] += runs
                    if lead_change:
                        apply_lead_change_swing(state)

                record_pitcher_stress(state, pitcher_id, spike=True)
                record_rally_progress(state, offense_team_id, batter_id, reached_base=True)
                apply_slump_boost(state, batter_id, was_slumping, "hit")
                maybe_catcher_settle(state, pitcher_id)

            break

    _broadcast_confidence_flashes(state)
    return