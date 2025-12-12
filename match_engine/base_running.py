from core.rng import get_rng
from match_engine.states import HitType
from world_sim.baserunning import (
    prepare_runner_state,
    resolve_steal_attempt as resolve_threat_steal,
)

rng = get_rng()


def _runner_speed(runner):
    if not runner:
        return 50
    return getattr(runner, 'running', getattr(runner, 'speed', 50)) or 50


def _aggression_bonus(state):
    """Teams push harder with two outs or when trailing late."""
    bonus = 0.0
    outs = getattr(state, "outs", 0) or 0
    inning = getattr(state, "inning", 1) or 1
    away_score = getattr(state, "away_score", 0) or 0
    home_score = getattr(state, "home_score", 0) or 0
    offense_is_home = getattr(state, "top_bottom", "Top") == "Bot"
    offense_score = home_score if offense_is_home else away_score
    defense_score = away_score if offense_is_home else home_score
    if outs == 2:
        bonus += 0.15
    if inning >= 7 and offense_score < defense_score:
        bonus += 0.10
    return bonus


def _arm_penalty(arm_rating: float | None) -> float:
    if arm_rating is None:
        return 0.0
    return (arm_rating - 50) * 0.004  # +/- 0.2 at extremes


def _depth_bonus(distance_ft: float | None, *, shallow_cutoff=180.0, deep_boost=240.0) -> float:
    if distance_ft is None:
        return 0.0
    if distance_ft < shallow_cutoff:
        return -0.12
    if distance_ft < 200:
        return -0.05
    if distance_ft > deep_boost:
        return 0.05
    return 0.0


def advance_runners(state, hit_type, batter, contact=None):
    """
    Moves runners based on hit type and (optionally) contact metadata.
    Updates state.runners and returns runs scored on this play.
    """
    scored_on_play = 0
    contact_meta = contact or {}
    ball_distance = getattr(contact_meta, "distance", None) if hasattr(contact_meta, "distance") else contact_meta.get("distance") if isinstance(contact_meta, dict) else None
    ball_type = getattr(contact_meta, "ball_type", None) if hasattr(contact_meta, "ball_type") else contact_meta.get("ball_type") if isinstance(contact_meta, dict) else None
    fielder_arm = getattr(contact_meta, "fielder_arm", None) if hasattr(contact_meta, "fielder_arm") else contact_meta.get("fielder_arm") if isinstance(contact_meta, dict) else None
    
    # Snapshot of who is where before moving
    r1 = state.runners[0] # 1st Base
    r2 = state.runners[1] # 2nd Base
    r3 = state.runners[2] # 3rd Base
    
    # Clear bases initially, we will repopulate them
    state.runners = [None, None, None]
    
    normalized_hit = hit_type
    if isinstance(normalized_hit, str) and normalized_hit in HitType._value2member_map_:
        normalized_hit = HitType(normalized_hit)

    if normalized_hit == HitType.HOMERUN:
        scored_on_play = 1 # Batter scores
        if r3: scored_on_play += 1
        if r2: scored_on_play += 1
        if r1: scored_on_play += 1
        # Bases remain empty

    elif normalized_hit == HitType.SINGLE:
        # R3 Scores
        if r3:
            scored_on_play += 1

        # R2 Logic: Score or stop at 3rd?
        if r2:
            runner_speed = _runner_speed(r2)
            score_chance = 0.45 + (runner_speed - 50) * 0.01 + _aggression_bonus(state)
            score_chance += _depth_bonus(ball_distance)
            score_chance -= _arm_penalty(fielder_arm)
            score_chance = min(0.95, max(0.25, score_chance))
            if rng.random() < score_chance:
                scored_on_play += 1  # Scored from 2nd on a single
            else:
                state.runners[2] = r2  # Stop at 3rd

        # R1 goes to 2nd (or 3rd on aggressive send)
        if r1:
            runner_speed = _runner_speed(r1)
            take_third_chance = 0.20 + (runner_speed - 50) * 0.009 + _aggression_bonus(state) * 0.6
            take_third_chance += _depth_bonus(ball_distance, shallow_cutoff=170.0, deep_boost=235.0)
            take_third_chance -= _arm_penalty(fielder_arm)
            take_third_chance = min(0.8, max(0.05, take_third_chance))
            if state.runners[2] is None and rng.random() < take_third_chance:
                state.runners[2] = r1  # 1st to 3rd
            else:
                state.runners[1] = r1  # Stop at 2nd

        # Batter to 1st
        state.runners[0] = batter

    elif normalized_hit == HitType.DOUBLE:
        # R3 Scores
        if r3: scored_on_play += 1
        # R2 Scores
        if r2: scored_on_play += 1
        
        # R1 Logic: Score or stop at 3rd?
        if r1:
            runner_speed = _runner_speed(r1)
            score_chance = 0.55 + (runner_speed - 50) * 0.01 + _aggression_bonus(state)
            score_chance += _depth_bonus(ball_distance, shallow_cutoff=200.0, deep_boost=260.0)
            score_chance -= _arm_penalty(fielder_arm)
            score_chance = min(0.97, max(0.3, score_chance))
            if rng.random() < score_chance:
                scored_on_play += 1 # Scored from 1st
            else:
                state.runners[2] = r1 # Stop at 3rd
        
        # Batter to 2nd
        state.runners[1] = batter

    elif normalized_hit == HitType.TRIPLE:
        if r3: scored_on_play += 1
        if r2: scored_on_play += 1
        if r1: scored_on_play += 1
        state.runners[2] = batter

    return scored_on_play

def resolve_steal_attempt(
    state,
    runner,
    pitcher,
    catcher,
    target_base,
    *,
    delivery_override: float | None = None,
    pop_override: float | None = None,
):
    """Bridge legacy call sites into the world_sim baserunning helpers."""

    if not runner:
        return False, "No runner to steal."

    base_lookup = {"2B": 0, "3B": 1}
    base_index = base_lookup.get(target_base, 0)
    threat = prepare_runner_state(state, base_index)
    if threat is None:
        return False, "Runner stays put."
    outcome = resolve_threat_steal(
        state,
        threat=threat,
        pitcher=pitcher,
        catcher=catcher,
        delivery_time=delivery_override,
        pop_time=pop_override,
    )
    return outcome.success, outcome.description
