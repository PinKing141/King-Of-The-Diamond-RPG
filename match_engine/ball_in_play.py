from game.rng import get_rng

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


class ContactResult:
    def __init__(self, hit_type, description, rbi=0, outs=0, credited_hit=True, error_on_play=False, primary_position=None):
        self.hit_type = hit_type # "Out", "1B", "2B", "3B", "HR"
        self.description = description
        self.rbi = rbi
        self.outs = outs
        self.credited_hit = credited_hit
        self.error_on_play = error_on_play
        self.primary_position = primary_position


def resolve_contact(contact_quality, batter, pitcher, state, power_mod=0):
    """
    Determines the result of a ball put in play.
    Uses contact_quality from pitch_logic + Batter Power + Randomness.
    Accepts 'power_mod' from User Input (Power Swing).
    """
    
    # Apply Power Mod (e.g. +25 from Power Swing)
    raw_power = batter.power + power_mod
    running = getattr(batter, 'running', getattr(batter, 'speed', 50))
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

    return ContactResult(hit_type, desc, credited_hit=credited_hit, error_on_play=error_on_play, primary_position=error_position)