from core.rng import get_rng
from game import stadiums
from match_engine.confidence import apply_fielding_error_confidence
from world.defense_profiles import get_defense_profile
from world_sim.fielding_engine import (
    FENCE_DISTANCE_FT,
    FieldingPlayResult,
    build_defense_alignment,
    resolve_fielding_play,
    simulate_batted_ball,
)
from game.fielding_system import run_fielding_event
from match_engine.states import HitType

rng = get_rng()

HOME_CONTACT_BONUS = 2
HOME_POWER_BONUS = 0
METERS_TO_FEET = 3.28084


def _pick_manual_fielder(ball, defenders):
    if not defenders:
        return None
    eligible = {"pitcher", "catcher", "first base", "second base", "shortstop", "third base"}
    if getattr(ball, "ball_type", "ground") != "ground":
        eligible = eligible | {"left field", "center field", "right field"}
    landing = (getattr(ball, "landing_x", 0.0), getattr(ball, "landing_y", 0.0))
    best = None
    best_dist = float("inf")
    for snap in defenders:
        if snap.position.lower() not in eligible:
            continue
        dist = (snap.x - landing[0]) ** 2 + (snap.y - landing[1]) ** 2
        if dist < best_dist:
            best = snap
            best_dist = dist
    return best


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _defense_team_id(state):
    if not state:
        return None
    if getattr(state, "top_bottom", "Top") == "Top":
        return getattr(state.home_team, "id", None)
    return getattr(state.away_team, "id", None)


def _human_controls_defense(state) -> bool:
    team_id = _defense_team_id(state)
    human_ids = getattr(state, "human_team_ids", set()) or set()
    return team_id in human_ids


def _user_controls_defense(state):
    return _defense_team_id(state) == 1 if state else False


def _offense_team_id(state):
    if not state:
        return None
    if getattr(state, "top_bottom", "Top") == "Top":
        return getattr(state.away_team, "id", None)
    return getattr(state.home_team, "id", None)


def _flow_multiplier(state, team_id):
    system = getattr(state, "momentum_system", None)
    if not system or team_id is None:
        return 1.0
    return system.get_multiplier(team_id)


def _stadium_from_state(state):
    if state is None:
        return stadiums.MUNICIPAL_FIELD
    name = getattr(state, "stadium_name", None) or getattr(state, "stadium", None)
    if isinstance(name, stadiums.StadiumPhysics):
        return name
    venue = getattr(state, "venue", None)
    venue_name = getattr(venue, "name", None) if venue else None
    return stadiums.get_stadium(name or venue_name)


def _spray_direction(angle: float) -> str:
    if angle <= -12:
        return "left"
    if angle >= 12:
        return "right"
    return "center"


def _runner_speed(runner):
    if not runner:
        return 50
    return getattr(runner, "running", getattr(runner, "speed", 50)) or 50


def _fence_profile(stadium_obj, spray_angle: float) -> tuple[float, float]:
    direction = _spray_direction(spray_angle)
    if direction == "left" and spray_angle > -22:
        dist_m = stadium_obj.distance_left_center
        height_m = stadium_obj.fence_height_left
    elif direction == "right" and spray_angle < 22:
        dist_m = stadium_obj.distance_right_center
        height_m = stadium_obj.fence_height_right
    elif direction == "left":
        dist_m = stadium_obj.distance_left
        height_m = stadium_obj.fence_height_left
    elif direction == "right":
        dist_m = stadium_obj.distance_right
        height_m = stadium_obj.fence_height_right
    else:
        dist_m = stadium_obj.distance_center
        height_m = stadium_obj.fence_height_center
    return dist_m * METERS_TO_FEET, height_m * METERS_TO_FEET


def _wall_outcome(ball, fence_distance_ft: float, fence_height_ft: float) -> str:
    if ball.landing_distance < fence_distance_ft:
        return "InPlay"
    margin = ball.landing_distance - fence_distance_ft
    if margin > 15.0:
        return "Home Run"
    estimated_height_at_wall = ball.apex_height * 0.4
    return "Home Run" if estimated_height_at_wall > fence_height_ft else "Wall Hit"


def _foul_pop_out(prob_scale: float, foul_ground_scale: float) -> bool:
    """Simple foul-pop resolution: larger foul ground means more outs."""
    chance = prob_scale * foul_ground_scale
    return rng.random() < chance


class ContactResult:
    def __init__(
        self,
        hit_type,
        description,
        rbi=0,
        outs=0,
        credited_hit=True,
        error_on_play=False,
        primary_position=None,
        *,
        runner_advances=None,
        special_play=None,
        extra_outs: int = 0,
        sacrifice: bool = False,
        rbi_credit: bool = False,
        error_type: str | None = None,
        distance: float | None = None,
        ball_type: str | None = None,
        fielder_arm: float | None = None,
    ):
        if isinstance(hit_type, HitType):
            self.hit_type = hit_type
        elif isinstance(hit_type, str) and hit_type in HitType._value2member_map_:
            self.hit_type = HitType(hit_type)
        else:
            self.hit_type = hit_type  # fallback for legacy values
        self.description = description
        self.rbi = rbi
        self.outs = outs
        self.credited_hit = credited_hit
        self.error_on_play = error_on_play
        self.primary_position = primary_position
        self.runner_advances = runner_advances
        self.special_play = special_play
        self.extra_outs = extra_outs
        self.sacrifice = sacrifice
        self.rbi_credit = rbi_credit
        self.error_type = error_type
        self.distance = distance
        self.ball_type = ball_type
        self.fielder_arm = fielder_arm


def resolve_contact(contact_quality, batter, pitcher, state, power_mod=0, trait_mods=None):
    """
    Determines the result of a ball put in play.
    Uses contact_quality from pitch_logic + Batter Power + Randomness.
    Accepts 'power_mod' from User Input (Power Swing).
    """
    
    # Apply Power Mod (e.g. +25 from Power Swing)
    trait_mods = trait_mods or {}
    raw_power = batter.power + trait_mods.get("power", 0) + power_mod
    running = getattr(batter, 'running', getattr(batter, 'speed', 50)) + trait_mods.get("speed", 0)
    offense_id = _offense_team_id(state)
    defense_id = _defense_team_id(state)
    flow_offense = _flow_multiplier(state, offense_id)
    flow_defense = _flow_multiplier(state, defense_id)
    pressure_index = getattr(state, "pressure_index", 0.0) if state else 0.0

    stadium_obj = _stadium_from_state(state)
    surface_friction = float(getattr(stadium_obj, "friction", 1.0) or 1.0)
    bounce_restitution = float(getattr(stadium_obj, "bounce_restitution", 1.0) or 1.0)
    bad_hop_chance = float(getattr(stadium_obj, "bad_hop_chance", 0.0) or 0.0)
    foul_ground_scale = float(getattr(stadium_obj, "foul_ground_scale", 1.0) or 1.0)
    wind_profile = (getattr(stadium_obj, "wind_profile", "") or "").lower()

    if flow_offense != 1.0:
        contact_quality *= flow_offense
        raw_power *= flow_offense
        running *= flow_offense
    if flow_defense != 1.0:
        contact_quality /= flow_defense

    batter_pressure = state.pressure_penalty(batter, "batter") if hasattr(state, "pressure_penalty") else 0.0
    if batter_pressure:
        penalty = max(0.55, 1.0 - batter_pressure)
        contact_quality *= penalty
        raw_power *= penalty
        running *= penalty

    pitcher_pressure = state.pressure_penalty(pitcher, "pitcher") if hasattr(state, "pressure_penalty") else 0.0
    if pitcher_pressure:
        contact_quality *= 1.0 + min(0.25, pitcher_pressure * 0.8)

    raw_power = max(15.0, raw_power)
    running = max(20.0, running)
    contact_quality = float(contact_quality)
    power_transfer = raw_power + rng.randint(0, 20)
    weather = getattr(state, 'weather', None)
    weather_effects = getattr(weather, 'effects', None)
    carry_shift = 0
    fly_distance_bonus_ft = 0.0
    ground_speed_bonus = 0.0
    error_scalar = 1.0

    trust_scalars = getattr(state, "fielding_trust_scalar", {}) or {}
    if trust_scalars and defense_id is not None:
        error_scalar *= trust_scalars.get(defense_id, 1.0)

    if weather:
        carry_shift = int((weather.carry_modifier or 0) * 35)
        contact_quality += int((weather.carry_modifier or 0) * 25)
        power_transfer += carry_shift
        error_scalar += getattr(weather, "error_modifier", 0.0) or 0.0

    if weather_effects:
        fly_distance_bonus_ft = weather_effects.fly_ball_distance_delta_m * 3.28084
        ground_speed_bonus = weather_effects.ground_ball_speed_bonus
        error_scalar += weather_effects.ball_slip_chance * 2.2

    # Surface physics: friction influences rollers; bad hops increase error pressure.
    ground_speed_bonus += (1.0 - surface_friction) * 12.0
    error_scalar *= 1.0 + bad_hop_chance * 0.6

    error_scalar = max(0.6, min(1.8, error_scalar))

    if state and getattr(state, "top_bottom", "Top") == "Bot":
        contact_quality += HOME_CONTACT_BONUS
        power_transfer += HOME_POWER_BONUS
    
    # Determine Trajectory
    if contact_quality < 35:
        trajectory = "Grounder"
    elif contact_quality < 65:
        trajectory = "Fly"
    elif contact_quality < 85:
        trajectory = "Line Drive"
    else:
        trajectory = "Gapper" if power_transfer < 80 else "Deep Fly"

    # Resolve Outcome based on Trajectory & Speed/Power
    # Map the abstract trajectory into physical launch parameters.
    launch_ranges = {
        "Grounder": (-5, 10),
        "Fly": (15, 30),
        "Line Drive": (10, 18),
        "Gapper": (20, 28),
        "Deep Fly": (28, 40),
    }
    launch_low, launch_high = launch_ranges.get(trajectory, (10, 25))
    launch_angle = rng.uniform(launch_low, launch_high)
    base_exit_vel = raw_power * 0.6 + contact_quality * 0.45 + rng.uniform(-5, 5)
    base_exit_vel *= max(0.9, min(1.1, bounce_restitution))
    if trajectory == "Grounder" and ground_speed_bonus:
        base_exit_vel += ground_speed_bonus
    exit_velocity = _clamp(base_exit_vel, 70, 115)
    spray = rng.uniform(-25, 25)
    bats = (getattr(batter, 'bats', 'R') or 'R').upper()
    spray += 6 if bats.startswith('L') else -6
    spray += getattr(batter, 'spray_tendency', 0) * 0.4
    spray_angle = _clamp(spray, -45, 45)

    fence_distance, fence_height = _fence_profile(stadium_obj, spray_angle)
    batted_ball = simulate_batted_ball(
        exit_velocity,
        launch_angle,
        spray_angle,
        fence_distance=fence_distance,
    )

    # Foul territory: high foul pops can become outs depending on space/hang time.
    if batted_ball.ball_type != "ground" and (spray_angle <= -45 or spray_angle >= 45):
        base_catch = 0.22 * foul_ground_scale
        base_catch += max(0.0, batted_ball.hang_time - 1.0) * 0.12
        base_catch = _clamp(base_catch, 0.05, 0.9)
        primary_pos = "third base" if spray_angle < 0 else "first base"
        if rng.random() < base_catch:
            desc = f"Foul pop near {primary_pos.title()}—caught!"
            return ContactResult(HitType.OUT, desc, credited_hit=False, primary_position=primary_pos.title(), distance=batted_ball.landing_distance, ball_type="foul_pop")
        desc = "Foul pop drifts out of play."
        return ContactResult("FOUL", desc, credited_hit=False, primary_position=primary_pos.title(), distance=batted_ball.landing_distance, ball_type="foul_pop")

    # Wind influence: modest nudge to distance/hang time by stadium profile.
    if wind_profile:
        if "hamikaze" in wind_profile:
            batted_ball.landing_distance *= 0.96
            batted_ball.hang_time *= 1.02
        elif "swirling" in wind_profile:
            delta = rng.uniform(-0.05, 0.05)
            batted_ball.landing_distance *= 1.0 + delta
            batted_ball.hang_time *= 1.0 + (delta / 2)
        elif "breeze" in wind_profile:
            batted_ball.landing_distance *= 1.01

    # Adjust grounders for surface friction and determine wall outcomes for flies.
    if batted_ball.ball_type == "ground":
        friction_scale = max(0.7, min(1.35, surface_friction))
        batted_ball.ground_time *= friction_scale
        batted_ball.landing_distance *= max(0.9, min(1.1, 1.0 + (1.0 - surface_friction) * 0.15))
    else:
        wall_result = _wall_outcome(batted_ball, fence_distance, fence_height)
        if wall_result == "Home Run":
            batted_ball.is_home_run = True
        elif wall_result == "Wall Hit":
            setattr(batted_ball, "wall_hit", True)
    defense_team = state.home_team if getattr(state, "top_bottom", "Top") == "Top" else state.away_team
    defense_profile = get_defense_profile(defense_team)
    alignment = build_defense_alignment(state, profile=defense_profile)
    if weather_effects and fly_distance_bonus_ft and batted_ball.ball_type != "ground":
        original_distance = max(1.0, batted_ball.landing_distance)
        new_distance = max(70.0, original_distance + fly_distance_bonus_ft)
        scale = new_distance / original_distance
        batted_ball.landing_distance = new_distance
        batted_ball.landing_x *= scale
        batted_ball.landing_y *= scale
        batted_ball.is_home_run = new_distance >= FENCE_DISTANCE_FT

    # Optional manual/user fielding hook: only when enabled and the defense is human-controlled.
    if getattr(state, "manual_fielding_prompts", False) and _human_controls_defense(state):
        fielding_play = _manual_fielding_override(
            state,
            batted_ball,
            alignment,
            runners=getattr(state, "runners", {}),
        )
    else:
        # Optional manual/user fielding hook: only when enabled and the defense is human-controlled.
        if getattr(state, "manual_fielding_prompts", False) and _human_controls_defense(state):
            fielding_play = _manual_fielding_override(
                state,
                batted_ball,
                alignment,
                runners=getattr(state, "runners", {}),
            )
        else:
            fielding_play = resolve_fielding_play(
                batted_ball,
                alignment,
                runner_speed=running,
                profile=defense_profile,
                environment_error_scalar=error_scalar,
                bad_hop_chance=bad_hop_chance,
            )

    raw_hit_type = fielding_play.hit_type
    if isinstance(raw_hit_type, HitType):
        hit_type = raw_hit_type
    elif isinstance(raw_hit_type, str) and raw_hit_type in HitType._value2member_map_:
        hit_type = HitType(raw_hit_type)
    else:
        hit_type = raw_hit_type
    desc = fielding_play.description
    if getattr(batted_ball, "wall_hit", False) and hit_type != HitType.OUT and not fielding_play.error_type:
        desc = "Caroms off the wall for extra bases."
    error_on_play = bool(fielding_play.error_type)
    credited_hit = not error_on_play and hit_type != HitType.OUT
    error_position = fielding_play.primary_position

    fielder_arm = None
    try:
        if alignment and fielding_play.primary_position:
            snap = next(
                (s for s in alignment if getattr(s, "position", "").lower() == str(fielding_play.primary_position).lower()),
                None,
            )
            if snap:
                fielder_arm = getattr(snap, "arm_rating", None)
    except Exception:
        fielder_arm = None

    if error_on_play:
        defense_id = _defense_team_id(state)
        if defense_id is not None:
            apply_fielding_error_confidence(state, defense_id, error_position)

    runner_advances = None
    extra_outs = 0
    ball_distance = getattr(batted_ball, "landing_distance", None)

    # Double-play chance on grounders with a force at 2B.
    if hit_type == HitType.OUT and getattr(batted_ball, "ball_type", "") == "ground":
        if getattr(state, "outs", 0) <= 1 and getattr(state, "runners", None):
            r1 = state.runners[0] if len(state.runners) > 0 else None
            if r1:
                dp_chance = 0.55
                dp_chance += (fielder_arm or 50 - 50) * 0.004
                dp_chance += 0.06 if (ball_distance or 0) <= 140 else 0.0  # sharply hit at infielders
                dp_chance -= (_runner_speed(r1) - 50) * 0.007
                dp_chance = max(0.25, min(0.85, dp_chance))
                if rng.random() < dp_chance:
                    extra_outs = 1
                    desc = desc + " (turned two)" if "two" not in desc.lower() else desc
                    runner_advances = [(0, -1, r1)]

    # Tag-up logic on deep fly outs.
    if hit_type == HitType.OUT and getattr(batted_ball, "ball_type", "") != "ground":
        runners = getattr(state, "runners", [])
        r3 = runners[2] if len(runners) > 2 else None
        r2 = runners[1] if len(runners) > 1 else None
        advances = []
        arm_penalty = (fielder_arm - 50) * 0.005 if fielder_arm is not None else 0.0
        if r3:
            chance = 0.40 + (_runner_speed(r3) - 50) * 0.01
            chance += (ball_distance or 0 - 220) * 0.0015
            chance -= arm_penalty
            chance = max(0.05, min(0.95, chance))
            if rng.random() < chance:
                advances.append((2, 3, r3))
        if r2:
            chance = 0.25 + (_runner_speed(r2) - 50) * 0.008
            chance += (ball_distance or 0 - 240) * 0.0012
            chance -= arm_penalty * 0.8
            chance = max(0.02, min(0.6, chance))
            if rng.random() < chance:
                advances.append((1, 2, r2))
        if advances:
            runner_advances = (runner_advances or []) + advances

    return ContactResult(
        hit_type,
        desc,
        credited_hit=credited_hit,
        error_on_play=error_on_play,
        primary_position=error_position,
        error_type=fielding_play.error_type,
        distance=ball_distance,
        ball_type=getattr(batted_ball, "ball_type", None),
        fielder_arm=fielder_arm,
        runner_advances=runner_advances,
        extra_outs=extra_outs,
    )


def _manual_fielding_override(state, batted_ball, alignment, runners) -> object:
    snap = _pick_manual_fielder(batted_ball, alignment)
    if snap is None:
        # No defender found, treat as missed play single
        return FieldingPlayResult(HitType.SINGLE, "No one there.")

    is_user = True  # only called when human defense
    if isinstance(runners, list):
        runner_dict = {1: bool(runners[0]) if len(runners) > 0 else False,
                       2: bool(runners[1]) if len(runners) > 1 else False,
                       3: bool(runners[2]) if len(runners) > 2 else False}
    else:
        runner_dict = {1: bool(runners.get(1)), 2: bool(runners.get(2)), 3: bool(runners.get(3))}
    res = run_fielding_event(
        snap.player or snap,
        is_user,
        "GROUNDER" if batted_ball.ball_type == "ground" else "FLYBALL",
        "INFIELD" if batted_ball.ball_type == "ground" else "OUTFIELD",
        runner_dict,
    )

    outcome = res.get("result_code", "SAFE")
    desc = res.get("narrative", "")

    if outcome == "OUT":
        return FieldingPlayResult(
            HitType.OUT,
            desc,
            primary_position=getattr(snap, "position", None),
            caught=True,
            fielded_clean=True,
            throw_completed=True,
        )

    if outcome == "ERROR":
        return FieldingPlayResult(
            HitType.SINGLE,
            desc or "Misplayed in the field.",
            primary_position=getattr(snap, "position", None),
            error_type="E_FIELD",
            fielded_clean=False,
        )

    # SAFE / HIT default: treat as single in play
    return FieldingPlayResult(
        HitType.SINGLE,
        desc or "Ball falls in for a hit.",
        primary_position=getattr(snap, "position", None),
    )
