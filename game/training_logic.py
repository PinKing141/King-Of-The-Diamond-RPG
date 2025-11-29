import random
import sys
import os

# Fix path to find utils.py in root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import PLAYER_ID
from .health_system import check_injury_risk, apply_injury, get_performance_modifiers
from database.setup_db import engine, Player, School 

def apply_scheduled_action(conn, action_type):
    """
    Executes a single action from the schedule.
    Updates stats, fatigue, and checks for injuries.
    Returns a summary string of what happened.
    """
    cursor = conn.cursor()
    
    # 1. Fetch Player + Role info
    cursor.execute("SELECT fatigue, growth_tag, conditioning, injury_days, jersey_number, position FROM players WHERE id = ?", (PLAYER_ID,))
    p_data = cursor.fetchone()
    
    if not p_data: return "Error: Player not found."
    
    fatigue = p_data[0]
    style = p_data[1]
    conditioning = p_data[2] if p_data[2] is not None else 50
    injury_days = p_data[3]
    jersey_num = p_data[4]
    position = p_data[5]
    
    # If injured, force rest (or specific rehab if implemented)
    if injury_days > 0:
        return f"Injured ({injury_days} days left). Cannot train."

    # 2. Get Global Modifiers (Good conditioning = better gains)
    mods = get_performance_modifiers(conditioning)
    
    summary = ""
    fatigue_change = 0
    stat_gains = {}

    # --- INJURY CHECK ---
    # Only rigorous physical activities have risk
    is_rigorous = action_type and (action_type.startswith('train_') or action_type in ['practice_match', 'team_practice', 'b_team_match'])
    
    if is_rigorous:
        intensity = 1.5 if 'match' in action_type else 1.0
        # Check risk (incorporating fatigue & conditioning)
        is_injured, severity = check_injury_risk(fatigue, intensity, conditioning)
        
        if is_injured:
            msg = apply_injury(conn, severity)
            return f"INJURY! {msg}"

    # --- ACTION HANDLERS ---
    
    # 1. REST
    if action_type == 'rest':
        # Conditioning affects recovery speed (Good cond = faster recovery)
        recovered = 30 * mods.get('stamina_recovery', 1.0)
        fatigue_change = -int(recovered)
        summary = f"Rest Day: Recovered {int(recovered)} fatigue."

    # 2. TEAM PRACTICE
    elif action_type == 'team_practice':
        fatigue_change = 15
        base_gain = 0.2 * mods.get('training_gain', 1.0)
        stat_gains = {'control': base_gain, 'power': base_gain, 'contact': base_gain, 'stamina': base_gain}
        summary = "Team Practice: General drills."

    # 3. A-TEAM MATCH (Practice Match)
    elif action_type == 'practice_match':
        # Matches are high cost, high reward
        fatigue_change = 25
        base_gain = 0.5 * mods.get('training_gain', 1.0)
        stat_gains = {'control': base_gain, 'velocity': base_gain/5, 'power': base_gain, 'contact': base_gain}
        summary = "A-Team Practice Match: Intense competition!"

    # 4. B-TEAM MATCH (New Feature)
    elif action_type == 'b_team_match':
        # Logic: If you are in the top 9 (Starter), this is too easy.
        # If you are 10-18 (Bench) or 99 (Reserve), this is valuable.
        # Assuming starters are jersey 1-9
        is_starter = (jersey_num is not None and jersey_num <= 9)
        
        if is_starter:
            fatigue_change = 20
            base_gain = 0.2 * mods.get('training_gain', 1.0)
            stat_gains = {'control': base_gain, 'stamina': base_gain}
            summary = "Played in B-Game. Too easy for a starter (Low gains)."
        else:
            # Reserves get GOOD XP here
            fatigue_change = 30
            base_gain = 0.7 * mods.get('training_gain', 1.0)
            stat_gains = {'control': base_gain, 'power': base_gain, 'contact': base_gain, 'fielding': base_gain}
            if position == "Pitcher":
                stat_gains['velocity'] = base_gain * 0.5
                stat_gains['stamina'] = base_gain
                
            summary = "B-Team Match: You fought hard to prove yourself! (High XP)"

    # 5. STUDY
    elif action_type == 'study':
        fatigue_change = 5
        # Academic stats if you had them, otherwise just time pass
        summary = "Study Session: Maintained academic standing."
        
    # 6. SOCIAL
    elif action_type == 'social':
        fatigue_change = 5
        # Morale boost could go here
        summary = "Social Activity: Reduced mental stress."
        
    # 7. MIND TRAINING
    elif action_type == 'mind':
        fatigue_change = -5 # Light recovery
        base_gain = 0.1 * mods.get('training_gain', 1.0)
        stat_gains = {'control': base_gain, 'contact': base_gain} 
        summary = "Mind & Focus: Visualisation training."

    # 8. SPECIFIC DRILLS
    elif action_type and action_type.startswith('train_'):
        # Efficiency drops if too tired
        efficiency = 1.0
        if fatigue > 50: efficiency = 0.7
        if fatigue > 80: efficiency = 0.3
        
        synergy = 1.0
        # Synergy: Bonus if drill matches Growth Style
        drill = action_type.replace('train_', '')
        
        if drill == 'control':
            stat_gains = {'control': 1.0}
            if style == 'Technical': synergy = 1.5
        elif drill == 'velocity':
            stat_gains = {'velocity': 0.3} # Vel is hard to raise
            if style == 'Power' or style == 'Pitcher': synergy = 1.5
        elif drill == 'stamina':
            stat_gains = {'stamina': 1.0}
            if style == 'Balanced': synergy = 1.2
        elif drill == 'power':
            stat_gains = {'power': 1.0}
            if style == 'Power': synergy = 1.5
        elif drill == 'contact':
            stat_gains = {'contact': 1.0}
            if style == 'Technical': synergy = 1.5
        elif drill == 'speed':
            stat_gains = {'speed': 1.0}
            if style == 'Speed': synergy = 1.5
            
        # Apply final calculation: Base * Efficiency * Synergy * Conditioning Mod
        for k in stat_gains:
            stat_gains[k] *= (efficiency * synergy * mods.get('training_gain', 1.0))
            
        fatigue_change = 10
        
        # Add feedback on conditioning for flavor text
        cond_note = ""
        gain_mult = mods.get('training_gain', 1.0)
        if gain_mult > 1.0: cond_note = " (Great Form!)"
        elif gain_mult < 1.0: cond_note = " (Sluggish...)"
        
        drill_name = drill.title()
        summary = f"Drill ({drill_name}): Session complete.{cond_note}"

    # --- DB UPDATE ---
    # 1. Update Fatigue
    new_fatigue = max(0, min(100, fatigue + fatigue_change))
    
    sql_parts = ["fatigue = ?"]
    sql_values = [new_fatigue]
    
    # 2. Update Stats
    for stat, value in stat_gains.items():
        # Add small randomness variance (0.9 - 1.1)
        variance = random.uniform(0.9, 1.1)
        final_value = value * variance
        
        # Check if stat column exists in DB logic (simplified here, assumes valid keys)
        sql_parts.append(f"{stat} = {stat} + ?")
        sql_values.append(final_value)
    
    sql_values.append(PLAYER_ID)
    
    if len(sql_parts) > 1 or fatigue_change != 0:
        sql_query = f"UPDATE players SET {', '.join(sql_parts)} WHERE id = ?"
        try:
            cursor.execute(sql_query, sql_values)
            conn.commit()
        except Exception as e:
            return f"Error updating stats: {e}"
    
    return summary

def run_training_camp_event(conn):
    # This is a stub or full function depending on if you want it in this file
    # Ideally, keep the implementation I gave in the previous turn here if you want it.
    pass