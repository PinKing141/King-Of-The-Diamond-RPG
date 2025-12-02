from game.rng import get_rng
from match_engine.confidence import apply_fielding_error_confidence
from player_roles.fielder_controls import prompt_hero_dive

rng = get_rng()

INFIELD_POSITIONS = [
    "Pitcher",
    "Catcher",
    "First Base",
    "Second Base",
    "Shortstop",
    "Third Base",
]
OUTFIELD_POSITIONS = ["Left Field", "Center Field", "Right Field"]

# Slight bump for home hitters; keep modest to avoid runaway scoring.
HOME_CONTACT_BONUS = 2
HOME_POWER_BONUS = 0


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


def _hero_defender_for_trajectory(trajectory: str) -> str:
    if trajectory == "Line Drive":
        return rng.choice(["Left Field", "Right Field"])
    if trajectory in {"Gapper", "Deep Fly"}:
        return "Center Field"
    return "Left Field"


def _is_gap_highlight_window(contact_quality: float, trajectory: str) -> bool:
    if trajectory not in {"Line Drive", "Gapper", "Deep Fly"}:
        return False
    return 70 <= contact_quality <= 90


def _ai_hero_dive_decision(state) -> str:
    pressure = getattr(state, "pressure_index", 0.0) or 0.0
    base = 0.35
    if pressure >= 7.0:
        base += 0.15
    if rng.random() < base:
        return "dive"
    return "safe"


def _maybe_handle_hero_dive(state, trajectory, hit_type, description, contact_quality):
    if hit_type == "Out" or not _is_gap_highlight_window(contact_quality, trajectory):
        return None
    defender = _hero_defender_for_trajectory(trajectory)
    if _user_controls_defense(state):
        decision = prompt_hero_dive(0.3, defender)
    else:
        decision = _ai_hero_dive_decision(state)
    logs = getattr(state, "logs", None) if state else None
    inning = getattr(state, "inning", 0) if state else 0
    half = getattr(state, "top_bottom", "Top") if state else "Top"
    if decision == "safe":
        if logs is not None:
            logs.append(f"[Field General] {defender} plays it safe, holding it to one. (Inning {half} {inning})")
        return ContactResult("1B", "Plays it on a hop to hold it to a single.", credited_hit=True, primary_position=defender)
    success = rng.random() <= 0.3
    if success:
        if logs is not None:
            logs.append(f"[Field General] {defender} lays out and robs a hit! (Inning {half} {inning})")
        return ContactResult("Out", "Laid out and snagged it!", outs=1, credited_hit=False, primary_position=defender)
    if logs is not None:
        logs.append(f"[Field General] Dive whiffs and it rolls to the wall! (Inning {half} {inning})")
    return ContactResult("3B", "Dives and misses! Ball rockets to the wall.", credited_hit=True, primary_position=defender)


def _apply_defensive_shift(state, trajectory, hit_type, description):
    shift = getattr(state, "defensive_shift", "normal")
    if shift == "double_play" and trajectory == "Grounder":
        if hit_type != "Out" and rng.random() < 0.4:
            return "Out", "Infield at double-play depth gobbles it up."
    elif shift == "infield_in" and trajectory == "Grounder":
        roll = rng.random()
        if hit_type != "Out" and roll < 0.4:
            return "Out", "Drawn-in infield cuts down the lead runner."
        if hit_type == "Out" and roll >= 0.4 and roll < 0.7:
            return "1B", "Hot shot bounces past the drawn-in infield."
    elif shift == "deep_outfield" and trajectory in {"Fly", "Gapper", "Deep Fly"}:
        if hit_type in {"2B", "3B", "HR"} and rng.random() < 0.5:
            return "1B", "Deep alignment limits it to a single."
        if hit_type == "1B" and rng.random() < 0.25:
            return "2B", "Shallow flare drops in front of the deep defense."
    return hit_type, description


class ContactResult:
    def __init__(self, hit_type, description, rbi=0, outs=0, credited_hit=True, error_on_play=False, primary_position=None):
        self.hit_type = hit_type # "Out", "1B", "2B", "3B", "HR"
        self.description = description
        self.rbi = rbi
        self.outs = outs
        self.credited_hit = credited_hit
        self.error_on_play = error_on_play
        self.primary_position = primary_position


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
    carry_shift = 0
    error_pressure = 0.0

    if weather:
        carry_shift = int((weather.carry_modifier or 0) * 35)
        contact_quality += int((weather.carry_modifier or 0) * 25)
        power_transfer += carry_shift
        error_pressure = weather.error_modifier
        if weather.precipitation in ("drizzle", "steady"):
            error_pressure += 0.03
        if weather.condition == "windy":
            error_pressure += 0.01

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
    hit_type = "Out"
    desc = "Out"
    credited_hit = True
    error_on_play = False
    error_position = None
    
    if trajectory == "Grounder":
        if contact_quality < 20:
            desc = "Weak dribbler to the mound."
        else:
            single_chance = 0.18 + max(0, contact_quality - 20) * 0.012
            single_chance += max(0, running - 55) * 0.003
            if rng.random() < min(0.55, single_chance):
                hit_type = "1B"
                if running > 72 and rng.random() < 0.35:
                    desc = "Infield single! Beat the throw."
                else:
                    desc = "Grounder finds a hole on the left side."
            else:
                desc = "Ground out."

    elif trajectory == "Fly":
        # Occasional bloop hits
        hit_roll = rng.random()
        bloop_chance = 0.10 + max(0, contact_quality - 40) * 0.008
        double_chance = 0.05 + max(0, power_transfer - 60) * 0.004
        if hit_roll < min(0.25, double_chance):
            hit_type = "2B"
            desc = "Blooper drops between outfielders for a hustle double."
        elif hit_roll < min(0.55, bloop_chance + double_chance):
            hit_type = "1B"
            desc = "Bloop single lands in no-man's land."
        else:
            desc = "Pop fly caught."

    elif trajectory == "Line Drive":
        line_drive_hit = 0.55 + max(0, contact_quality - 60) * 0.01
        if rng.random() < min(0.9, line_drive_hit):
            if power_transfer > 95 and rng.random() < 0.15:
                hit_type = "2B"
                desc = "Laser ropes down the line for a double."
            else:
                hit_type = "1B"
                desc = "Clean single to center."
        else:
            desc = "Line drive... CAUGHT!"

    elif trajectory == "Gapper":
        gap_double = 0.55 + max(0, running - 50) * 0.005
        if rng.random() < min(0.95, gap_double):
            hit_type = "2B"
            desc = "Double into the gap!"
        else:
            hit_type = "1B"
            desc = "Long single off the wall."

    elif trajectory == "Deep Fly":
        homer_line = 82 - carry_shift  # better carry => easier HR
        if power_transfer > homer_line:
            hit_type = "HR"
            desc = "HOME RUN! Gone!"
        elif power_transfer > homer_line - 10:
            hit_type = "2B"
            desc = "Off the wall! Double."
        else:
            desc = "Deep fly out at the warning track."

    hit_type, desc = _apply_defensive_shift(state, trajectory, hit_type, desc)
    hero_result = _maybe_handle_hero_dive(state, trajectory, hit_type, desc, contact_quality)
    if hero_result:
        return hero_result

    if hit_type == "Out":
        error_chance = 0.0
        if trajectory == "Grounder":
            error_chance += 0.02
        elif trajectory in ("Fly", "Deep Fly"):
            error_chance += 0.01
        if weather:
            error_chance += max(0.0, error_pressure)
            if weather.precipitation in ("drizzle", "steady"):
                error_chance += 0.04
            if weather.condition == "windy" and trajectory in ("Fly", "Deep Fly"):
                error_chance += 0.02
        if pressure_index > 0:
            error_chance += max(0.0, pressure_index - 4.0) * 0.01
        if flow_defense > 1.0:
            error_chance /= flow_defense
        if rng.random() < min(0.4, error_chance):
            hit_type = "1B"
            desc = "Mishandled in the field! Batter reaches on the error."
            credited_hit = False
            error_on_play = True
            if trajectory in ("Fly", "Deep Fly"):
                error_position = rng.choice(OUTFIELD_POSITIONS)
            elif trajectory == "Line Drive":
                error_position = rng.choice(OUTFIELD_POSITIONS + INFIELD_POSITIONS[2:])
            else:
                error_position = rng.choice(INFIELD_POSITIONS)
            defense_id = _defense_team_id(state)
            if defense_id is not None:
                apply_fielding_error_confidence(state, defense_id, error_position)

    return ContactResult(hit_type, desc, credited_hit=credited_hit, error_on_play=error_on_play, primary_position=error_position)