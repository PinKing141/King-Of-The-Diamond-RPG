"""
battery_system/battery_profiles.py

Procedural generation of Battery Titles.
Only assigns names to 'Elite' or 'Extreme' pairs.
Average batteries return None (no title).
"""
from game.battery_mechanics import calculate_catch_difficulty
from ui.ui_display import Colour
import random

# --- NAMING POOLS ---

ELITE_ADJECTIVES = ["Iron", "Golden", "Diamond", "Perfect", "Supreme", "Royal", "Unbroken"]
ELITE_NOUNS = ["Battery", "Wall", "Engine", "Fortress", "Guard", "Standard", "Crown"]

FAST_ADJECTIVES = ["Velocity", "Lightning", "Thunder", "Mach", "Rapid", "Turbo"]
FAST_NOUNS = ["Kings", "Force", "Drive", "Rush", "Ignition"]

WILD_ADJECTIVES = ["Chaos", "Wild", "Broken", "Erratic", "Panic", "Risky"]
WILD_NOUNS = ["Factor", "Storm", "Dice", "Hazard", "Ride"]

SUB_ADJECTIVES = ["Phantom", "Ghost", "Low", "Unders", "Submarine"]
SUB_NOUNS = ["Dive", "Assassins", "Shadows", "Current"]


def _generate_name(adj_pool, noun_pool):
    """Simple combinatorial name generator."""
    return f"{random.choice(adj_pool)} {random.choice(noun_pool)}"


def get_battery_identity(pitcher, catcher, trust=50, mech_profile=None):
    """
    Analyzes the pair and returns a tuple (Title, Color) OR (None, None).

    Logic:
    1. Check for 'Extreme' Physics (Wildness / Velo / Slot).
    2. Check for 'Elite' Defense (Catcher Wall).
    3. Check for 'High' Trust.

    If none of these thresholds are met, returns None.
    """
    if not pitcher or not catcher:
        return None, None

    # --- 1. Gather Stats ---
    p_velo = getattr(pitcher, "velocity", 130)
    p_ctrl = getattr(pitcher, "control", 50)

    c_wall = getattr(catcher, "catcher_ability", 50)
    c_arm = getattr(catcher, "throwing", 50)

    # Calculate 'Volatility' (Physics Difficulty)
    # If mech_profile is missing, assume standard (50)
    volatility = 50.0
    if mech_profile:
        volatility = calculate_catch_difficulty(mech_profile)

    # --- 2. Threshold Checks ---

    is_elite_wall = c_wall >= 85
    is_elite_arm = c_arm >= 85
    is_flamethrower = p_velo >= 153
    is_control_god = p_ctrl >= 85
    is_wild = p_ctrl <= 40 or volatility >= 75
    is_submarine = mech_profile and mech_profile.arm_slot == "Submarine"
    is_high_trust = trust >= 90

    # --- 3. Name Generation Logic (Priority Order) ---

    # A. THE "PERFECT BATTERY" (High Trust + Elite Skills)
    if is_high_trust and is_elite_wall and is_control_god:
        # e.g., "The Diamond Battery"
        return _generate_name(ELITE_ADJECTIVES, ELITE_NOUNS), Colour.GOLD

    # B. THE "TAMED BEAST" (Wild Pitcher + Elite Catcher)
    # This is a specific RPG archetype: The Catcher saves the Pitcher.
    if is_wild and is_elite_wall:
        return "The Tamed Beast", Colour.CYAN

    # C. THE "DISASTER" (Wild Pitcher + Bad Catcher)
    # The game warns you this is a bad idea.
    if is_wild and c_wall < 50:
        return _generate_name(WILD_ADJECTIVES, WILD_NOUNS), Colour.RED

    # D. THE "VELOCITY KINGS" (Fast Pitcher + Strong Arm)
    # You can't hit it, and you can't run on it.
    if is_flamethrower and is_elite_arm:
        return _generate_name(FAST_ADJECTIVES, FAST_NOUNS), Colour.RED

    # E. THE "SUBMARINE SPECIALISTS" (Submarine + Counter-Trait)
    # Check if catcher has the trait to handle low balls
    c_traits = getattr(catcher, "traits", []) or []
    if is_submarine and "low_ball_framer" in c_traits:
        return _generate_name(SUB_ADJECTIVES, SUB_NOUNS), Colour.PURPLE

    # F. THE "SNIPERS" (Low Velo + Elite Control + Elite Framing)
    if p_velo < 135 and is_control_god and is_elite_wall:
        return "The Frame Artists", Colour.BLUE

    # --- 4. Fallback ---
    # If they are just "Good" (e.g., 70 stats) but not "Elite",
    # they get no name. This keeps the names special.
    return None, None
