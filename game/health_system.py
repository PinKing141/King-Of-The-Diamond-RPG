import random
from typing import Optional, Union

from sqlalchemy.orm import Session

from database.setup_db import Player
from game.game_context import GameContext

# --- CONDITIONING STATES ---
COND_POOR_THRESH = 30
COND_GOOD_THRESH = 70

def get_conditioning_state(value):
    if value <= COND_POOR_THRESH: return "POOR"
    if value >= COND_GOOD_THRESH: return "GOOD"
    return "NORMAL"

def get_performance_modifiers(conditioning):
    state = get_conditioning_state(conditioning)
    if state == "POOR":
        return {"injury_risk_mult": 1.5, "training_gain": 0.8, "match_perf": 0.9}
    elif state == "GOOD":
        return {"injury_risk_mult": 0.8, "training_gain": 1.2, "match_perf": 1.1}
    return {"injury_risk_mult": 1.0, "training_gain": 1.0, "match_perf": 1.0}

def get_conditioning_feedback(value):
    state = get_conditioning_state(value)
    if state == "GOOD":
        return random.choice([
            "Your body feels light today.",
            "Coach: 'You're moving well lately.'",
            "You feel sharp and energised."
        ])
    elif state == "POOR":
        return random.choice([
            "You feel unusually stiff.",
            "Coach: 'Your reactions have slowed.'",
            "Your body feels heavy and sluggish."
        ])
    return "" # Normal state has no feedback (invisible baseline)

def check_injury_risk(fatigue, intensity, conditioning):
    mods = get_performance_modifiers(conditioning)
    risk_chance = 0.01 * mods['injury_risk_mult']
    
    if fatigue > 80: risk_chance += (0.20 * mods['injury_risk_mult'])
    elif fatigue > 50: risk_chance += (0.05 * mods['injury_risk_mult'])
    
    risk_chance *= intensity
    
    if random.random() < risk_chance:
        roll = random.random()
        severity = "Minor"
        if roll < 0.85: severity = "Minor"
        elif roll < 0.95: severity = "Moderate"
        else: severity = "Severe"
        return True, severity
    return False, None


def _get_player(context: GameContext) -> Optional[Player]:
    if context.player_id is None:
        return None
    return context.session.get(Player, context.player_id)


def apply_injury(context_or_session: Union[GameContext, Session], severity, player: Optional[Player] = None):
    """Apply an injury to either the context player or a provided Player object."""
    if isinstance(context_or_session, GameContext):
        session = context_or_session.session
        target_player = player or _get_player(context_or_session)
    elif isinstance(context_or_session, Session):
        session = context_or_session
        target_player = player
    else:
        raise ValueError("apply_injury requires a GameContext or Session.")

    if not target_player:
        return "Error: player not found."

    desc = {"Minor": "Muscle Strain", "Moderate": "Sprain", "Severe": "Fracture"}
    days = {"Minor": 3, "Moderate": 14, "Severe": 60}

    d = days.get(severity, 3)

    target_player.injury_days = d
    session.add(target_player)
    session.commit()

    return f"(!) INJURY: {desc.get(severity, 'Unknown')} ({severity}). Out for {d} days."

def calculate_weekly_conditioning_update(context: GameContext, schedule_grid, avg_fatigue):
    """
    Analyzes the week's behaviour to adjust the invisible Conditioning stat.
    Called at the end of the week in main_loop (or weekly_scheduler).
    """
    player = _get_player(context)
    if not player:
        return 0, "UNKNOWN"

    current_cond = player.conditioning if player.conditioning is not None else 50
    
    change = 0
    
    # --- ANALYSIS COUNTERS ---
    heavy_train_count = 0
    rest_count = 0
    mind_social_count = 0
    
    for day in schedule_grid:
        for slot in day:
            if not slot: continue
            if 'power' in slot or 'speed' in slot or 'stamina' in slot or 'match' in slot:
                heavy_train_count += 1
            elif slot == 'rest':
                rest_count += 1
            elif slot in ['mind', 'social']:
                mind_social_count += 1

    # --- RULE 1: Overtraining Penalty ---
    # More than 10 heavy sessions a week is pushing it
    if heavy_train_count > 12:
        change -= 5
    elif heavy_train_count > 15:
        change -= 10 # Severe penalty for grinding without breaks

    # --- RULE 2: Recovery Bonus ---
    if rest_count >= 3: # Reasonable rest
        change += 2
    if rest_count >= 5: # Well rested
        change += 3
        
    # --- RULE 3: Mental/Social Balance ---
    if mind_social_count >= 2:
        change += 2 # Stress reduction helps physical health

    # --- RULE 4: Fatigue Management ---
    # If player spent the week exhausted (avg_fatigue > 70), body breaks down
    if avg_fatigue > 80:
        change -= 5
    elif avg_fatigue < 40:
        change += 2

    # Apply Update
    new_cond = max(0, min(100, current_cond + change))
    player.conditioning = new_cond
    context.session.add(player)
    context.session.commit()
    
    return change, get_conditioning_state(new_cond)