"""
Calculates the "Physics" of the battery relationship:
- Catch Difficulty (Volatility) based on Arm Slot/Deception
- Pass Ball / Wild Pitch Resolution
- Runner Hold Ratings
- Stamina Efficiency based on mechanics
"""
from __future__ import annotations

import random
from typing import Optional, Tuple

# --- CONFIGURATION ---
# Base difficulty penalty (0-100 scale) for catching different slots
SLOT_DIFFICULTY = {
    "Over-the-Top": 5.0,        # Predictable drop
    "Three-Quarters": 10.0,     # Standard tail
    "Low Three-Quarters": 20.0, # Late lateral movement
    "Sidearm": 35.0,            # Heavy horizontal run (Hardest to frame)
    "Submarine": 45.0,          # Rising/Sinking chaos
}


def calculate_catch_difficulty(
    profile,  # PitchingMechanicsProfile
    pitch_type: str = "Fastball",
    pitch_location: str = "Zone",
) -> float:
    """
    Returns a 'Volatility Score' (0.0 - 100.0+) representing how hard
    the pitch is to block or frame.
    """
    if not profile:
        return 10.0

    # 1. Base difficulty from the Arm Slot
    # Default to Three-Quarters if slot is missing/custom
    base_volatility = SLOT_DIFFICULTY.get(profile.arm_slot, 10.0)

    # 2. Deception Penalty
    # A highly deceptive pitcher (1.2+) adds visual noise for the catcher too.
    # Formula: (Deception - 0.6 baseline) * 25
    vision_penalty = max(0, (profile.deception - 0.6) * 25.0)

    # 3. Balance Mitigation (Control Stability)
    # High balance (1.2) reduces the chance of erratic misses.
    # Low balance (<0.5) spikes the risk of a "non-competitive" pitch.
    stability_bonus = (profile.balance - 0.5) * -20.0

    # 4. Contextual Multipliers
    multiplier = 1.0

    # Horizontal pitches from horizontal slots are nightmares (Frisbee sliders)
    if profile.arm_slot in {"Sidearm", "Low Three-Quarters"}:
        if pitch_type in {"Slider", "Sweeper", "Slurve", "Shuuto"}:
            multiplier = 1.3

    # Vertical drops from Over-the-Top are hard to block (Spikes)
    if profile.arm_slot == "Over-the-Top":
        if pitch_type in {"Curveball", "Forkball", "Splitter"} and "Low" in pitch_location:
            multiplier = 1.4

    # Submarine Rise Effect
    if profile.arm_slot == "Submarine" and pitch_type in {"4-Seam Fastball", "High Fastball"}:
        multiplier = 1.25

    total_volatility = (base_volatility + vision_penalty + stability_bonus) * multiplier

    # Clamp to reasonable risk (Min 5% chance of tough block, Max 95%)
    return max(5.0, min(95.0, total_volatility))


def resolve_pass_ball_check(
    volatility: float,
    catcher_wall: int,
    catcher_traits: Tuple[str, ...] = (),
) -> str:
    """
    Determines the outcome of a pitch in the dirt or missed spot.

    Returns:
        'Clean'  - Caught/Framed perfectly
        'Block'  - Blocked in dirt (Ball count, no advance)
        'Pass'   - Passed Ball (Runner advance, Catcher fault)
        'Wild'   - Wild Pitch (Runner advance, Pitcher fault)
    """
    # 1. Calculate Effective Wall
    effective_wall = float(catcher_wall)

    # Trait Bonuses
    if "iron_wall_blocker" in catcher_traits:
        effective_wall += 15
    elif "vacuum_blocker" in catcher_traits:
        # Bonus specifically against high volatility (bad pitches)
        effective_wall += volatility * 0.25

    # Slot-Specific Counters
    # (Assuming the caller handles checking if the catcher has the RIGHT trait for the slot)
    # But generally, high wall absorbs all.

    # 2. The Check: Volatility vs Wall
    # If Volatility > Effective Wall, risk exists.
    risk_delta = volatility - effective_wall

    # Safe Zone: Catcher is much better than the pitch's wildness
    if risk_delta <= -15:
        return "Clean"

    roll = random.uniform(0, 100)

    # Danger Zone (Pitch is wilder than catcher is good)
    if risk_delta > 0:
        # High chance of failure
        # Example: Volatility 80 (Wild Sidearm) vs Wall 50 (Avg) = Delta 30
        # 30% chance to fail catch
        if roll < (risk_delta * 0.8):
            # Is it a Pass Ball or Wild Pitch?
            # If volatility came mostly from mechanics (Wild), it's Wild Pitch.
            # If it was catchable but dropped, Pass Ball.
            return "Wild" if volatility > 70 else "Pass"
        elif roll < (risk_delta * 1.3):
            return "Block"  # Saved it!
    else:
        # Safe Zone, but random bad hops happen (Low probability)
        if roll < 1.5:
            return "Pass"

    return "Clean"


def calculate_hold_rating(profile) -> float:
    """
    Calculates how well this mechanics profile holds runners.
    Returns 0-100 rating.
    """
    if not profile:
        return 50.0

    # Base average
    hold = 50.0

    # Tempo Bonus: Faster tempo = less lead time
    # Tempo 1.2 (+35) vs Tempo 0.2 (-15)
    hold += (profile.tempo - 0.5) * 50.0

    # Posture Bonus
    if profile.posture == "closed":
        hold += 12.0  # Hides the knee pop/move to first
    elif profile.posture == "open":
        hold -= 8.0  # Easier to read first move

    # Slot Factor: Sidearmers often have quicker slide steps but easier reads
    if profile.arm_slot == "Sidearm":
        hold -= 5.0

    return max(0.0, min(100.0, hold))


def calculate_stamina_efficiency(profile) -> float:
    """
    Returns a multiplier for stamina drain per pitch.
    1.0 = Standard
    >1.0 = High Effort (Drains faster)
    <1.0 = Efficient (Lasts longer)
    """
    if not profile:
        return 1.0

    # Aggression: Max effort deliveries cost more energy
    aggression_cost = (profile.aggression - 0.5) * 0.4

    # Balance: Good mechanics save energy / prevent leaks
    balance_save = (profile.balance - 0.5) * 0.25

    # Tempo: Extremes cost energy. Smooth (0.5-0.7) is efficient.
    tempo_penalty = 0.0
    if profile.tempo > 1.1:
        tempo_penalty = 0.08  # Rushed
    if profile.tempo < 0.3:
        tempo_penalty = 0.05  # Laborious

    base_drain = 1.0 + aggression_cost - balance_save + tempo_penalty
    return max(0.7, min(1.4, base_drain))
