from game.rng import get_rng
from match_engine.confidence import apply_fielding_error_confidence
from world.defense_profiles import get_defense_profile
from world_sim.fielding_engine import (
    FENCE_DISTANCE_FT,
    build_defense_alignment,
    resolve_fielding_play,
    simulate_batted_ball,
)

rng = get_rng()

HOME_CONTACT_BONUS = 2
HOME_POWER_BONUS = 0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _defense_team_id(state):
    if not state:
        return None
    if getattr(state, "top_bottom", "Top") == "Top":
        return getattr(state.home_team, "id", None)
    return getattr(state.away_team, "id", None)


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
    ):
        self.hit_type = hit_type # "Out", "1B", "2B", "3B", "HR"
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
    if trajectory == "Grounder" and ground_speed_bonus:
        base_exit_vel += ground_speed_bonus
    exit_velocity = _clamp(base_exit_vel, 70, 115)
    spray = rng.uniform(-25, 25)
    bats = (getattr(batter, 'bats', 'R') or 'R').upper()
    spray += 6 if bats.startswith('L') else -6
    spray += getattr(batter, 'spray_tendency', 0) * 0.4
    spray_angle = _clamp(spray, -45, 45)

    batted_ball = simulate_batted_ball(exit_velocity, launch_angle, spray_angle)
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

    fielding_play = resolve_fielding_play(
        batted_ball,
        alignment,
        runner_speed=running,
        profile=defense_profile,
        environment_error_scalar=error_scalar,
    )

    hit_type = fielding_play.hit_type
    desc = fielding_play.description
    error_on_play = bool(fielding_play.error_type)
    credited_hit = not error_on_play and hit_type != "Out"
    error_position = fielding_play.primary_position

    if error_on_play:
        defense_id = _defense_team_id(state)
        if defense_id is not None:
            apply_fielding_error_confidence(state, defense_id, error_position)

    return ContactResult(
        hit_type,
        desc,
        credited_hit=credited_hit,
        error_on_play=error_on_play,
        primary_position=error_position,
        error_type=fielding_play.error_type,
    )