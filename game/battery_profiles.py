"""
game/battery_profiles.py

Analyzes a Pitcher/Catcher pair to generate a narrative archetype.
This provides the "Scouting Report" title and description.
"""
from ui.ui_display import Colour
from game.battery_mechanics import calculate_catch_difficulty


def analyze_battery_chemistry(pitcher, catcher, trust_score=50, mech_profile=None):
    """
    Returns a tuple (Title, Description, Color) for the battery.
    """
    # --- 1. Pitcher Analysis ---
    velo = getattr(pitcher, "velocity", 130)
    ctrl = getattr(pitcher, "control", 50)
    # Determine base type
    if velo > 152:
        p_type = "Flame"
    elif velo < 135 and ctrl > 70:
        p_type = "Finesse"
    elif ctrl < 40:
        p_type = "Wild"
    elif mech_profile and mech_profile.arm_slot == "Submarine":
        p_type = "Sub"
    elif mech_profile and mech_profile.arm_slot == "Sidearm":
        p_type = "Side"
    else:
        p_type = "Standard"

    # --- 2. Catcher Analysis ---
    wall = getattr(catcher, "catcher_ability", 50)  # The "Wall" Stat
    arm = getattr(catcher, "throwing", 50)
    # Determine base type
    if wall > 80:
        c_type = "Iron"
    elif wall < 45:
        c_type = "Paper"
    elif arm > 80:
        c_type = "Cannon"
    else:
        c_type = "Standard"

    # --- 3. Physics Check ---
    # How hard is this specific pitcher for a generic catcher?
    volatility = 50.0
    if mech_profile:
        volatility = calculate_catch_difficulty(mech_profile)

    # --- 4. Trait Checks ---
    p_traits = getattr(pitcher, "traits", []) or []
    c_traits = getattr(catcher, "traits", []) or []

    has_trust_trait = "trust_the_mitt" in p_traits
    has_framer = "pitch_framer" in c_traits
    has_low_framer = "low_ball_framer" in c_traits
    is_shaker = "shake_off_king" in p_traits

    # --- 5. Archetype Logic (The "Infinite" Generator) ---
    title = "Standard Battery"
    desc = "A balanced pitcher and catcher pairing."
    color = Colour.WHITE

    # A. The "Physics Wars" (Volatility vs Wall)
    if volatility > 70 and c_type == "Iron":
        title = "The Tamed Beast"
        desc = "Elite blocking allows the pitcher's chaotic stuff to thrive."
        color = Colour.GOLD
    elif volatility > 70 and c_type == "Paper":
        title = "Disaster Risk"
        desc = "The catcher cannot handle the pitcher's movement. Expect passed balls."
        color = Colour.RED

    # B. The Slot Specialists
    elif p_type == "Sub" and has_low_framer:
        title = "The Low-Ball Magicians"
        desc = "Perfect synergy for the submarine delivery."
        color = Colour.CYAN
    elif p_type == "Sub" and c_type == "Paper":
        title = "The Frisbee Discord"
        desc = "Catcher is struggling to track the rising release point."
        color = Colour.YELLOW

    # C. Velocity Archetypes
    elif p_type == "Flame" and c_type == "Cannon":
        title = "The Power Battery"
        desc = "Overpowering velocity and an arm to match. Don't run."
        color = Colour.RED
    elif p_type == "Flame" and c_type == "Iron":
        title = "The Safety Valve"
        desc = "Pitcher throws heat; Catcher stops the leaks."
        color = Colour.GREEN

    # D. Finesse Archetypes
    elif p_type == "Finesse" and has_framer:
        title = "The Frame Artists"
        desc = "Expanding the strike zone inch by inch."
        color = Colour.PURPLE

    # E. Trust Dynamics
    if trust_score > 90:
        title = f"Telepathic {title}"
    elif trust_score < 25:
        title = f"Dysfunctional {title}"
        if is_shaker:
            desc += " The pitcher refuses to listen to signs."

    return title, desc, color
