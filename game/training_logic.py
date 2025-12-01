import logging
import os
import random
from typing import List, Optional

from .health_system import check_injury_risk, apply_injury, get_performance_modifiers
from database.setup_db import Player
from game.academic_system import resolve_study_session, clamp, is_academically_eligible
from game.game_context import GameContext
from game.personality_effects import adjust_player_morale, decay_slump
from game.player_progression import MilestoneUnlockResult, process_milestone_unlocks
from game.relationship_manager import register_morale_rebound
from game.skill_system import check_and_grant_skills
from game.trait_logic import get_progression_speed_multiplier
from ui.ui_display import Colour

logger = logging.getLogger(__name__)
PROGRESSION_DEBUG = os.getenv("PROGRESSION_DEBUG", "").lower() in {"1", "true", "yes"}


def _get_player(context: GameContext) -> Optional[Player]:
    if context.player_id is None:
        return None
    return context.session.get(Player, context.player_id)


def _apply_temp_training_bonuses(context: GameContext, stat_gains: dict):
    if not context or not stat_gains:
        return
    bonus = context.get_temp_effect('mentor_training')
    if not bonus:
        return
    multiplier = 1 + bonus.get('multiplier', 0.0)
    for stat in stat_gains:
        stat_gains[stat] *= multiplier


def apply_scheduled_action(context: GameContext, action_type: str) -> dict:
    """Execute a scheduled action and return a structured result dict."""
    player = _get_player(context)
    if not player:
        return {"status": "error", "message": "Player not found."}
    
    fatigue = player.fatigue or 0
    style = player.growth_tag or "Normal"
    conditioning = player.conditioning if player.conditioning is not None else 50
    injury_days = player.injury_days or 0
    jersey_num = player.jersey_number
    position = player.position
    is_academic_ok = is_academically_eligible(player, player.school)
    
    # If injured, force rest (or specific rehab if implemented)
    if injury_days > 0:
        return {
            "status": "skipped",
            "message": f"Injured ({injury_days} days left). Cannot train.",
            "fatigue_change": 0,
            "stat_changes": {},
        }

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
            msg = apply_injury(context, severity)
            return {
                "status": "injured",
                "message": f"INJURY! {msg}",
                "fatigue_change": 0,
                "stat_changes": {},
            }

    # Academic suspension blocks competitive matches entirely
    match_actions = {'practice_match', 'b_team_match'}
    if action_type in match_actions and not is_academic_ok:
        return {
            "status": "skipped",
            "message": "Academic suspension: Coaches won't let you suit up.",
            "fatigue_change": 0,
            "stat_changes": {},
        }

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
        outcome = resolve_study_session(player, fatigue)
        fatigue_change = outcome.fatigue_cost
        stat_gains = {
            'academic_skill': outcome.academic_gain,
            'test_score': outcome.test_gain,
        }
        summary = outcome.summary
        
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

    # Slump dampening / recovery
    slump_timer = getattr(player, 'slump_timer', 0) or 0
    if slump_timer > 0:
        if action_type == 'rest':
            stat_gains = {k: v * 0.8 for k, v in stat_gains.items()}
            fatigue_change -= 3
        else:
            stat_gains = {k: v * 0.6 for k, v in stat_gains.items()}
            summary += " Confidence slump slows your rhythm."

    # --- DB UPDATE ---
    _apply_temp_training_bonuses(context, stat_gains)
    progression_mult = get_progression_speed_multiplier(player)
    if stat_gains and progression_mult != 1.0:
        for stat in list(stat_gains.keys()):
            stat_gains[stat] *= progression_mult
    # 1. Update Fatigue
    new_fatigue = max(0, min(100, fatigue + fatigue_change))
    player.fatigue = new_fatigue

    for stat, value in stat_gains.items():
        variance = random.uniform(0.9, 1.1)
        final_value = value * variance
        current = getattr(player, stat, 0) or 0
        setattr(player, stat, current + final_value)

    if 'academic_skill' in stat_gains:
        player.academic_skill = int(round(clamp(player.academic_skill or 0, 25, 110)))
    if 'test_score' in stat_gains:
        player.test_score = int(round(clamp(player.test_score or 0, 0, 100)))

    if slump_timer > 0:
        resolved = decay_slump(player)
        if resolved:
            adjust_player_morale(player, 4)
            register_morale_rebound(context.session, player, reason="slump_cleared")
            summary += " (You finally shake the slump.)"

    unlocked_skills = check_and_grant_skills(context.session, player)
    milestone_unlocks = process_milestone_unlocks(context.session, player)
    if milestone_unlocks:
        unlocked_skills.extend(entry.skill_name for entry in milestone_unlocks)
        _announce_milestones(milestone_unlocks)
        if PROGRESSION_DEBUG:
            logger.info(
                "Training action %s for player %s triggered milestones %s",
                action_type,
                getattr(player, "id", "unknown"),
                [entry.milestone_key for entry in milestone_unlocks],
            )

    if unlocked_skills:
        names = ", ".join(unlocked_skills)
        summary += f" New skill unlocked: {names}."
        if PROGRESSION_DEBUG:
            logger.info(
                "Training action %s for player %s granted skills %s",
                action_type,
                getattr(player, "id", "unknown"),
                unlocked_skills,
            )

    context.session.add(player)
    context.session.commit()

    return {
        "status": "ok",
        "message": summary,
        "fatigue_change": fatigue_change,
        "stat_changes": stat_gains,
        "new_fatigue": new_fatigue,
        "skills_unlocked": unlocked_skills,
        "milestones": milestone_unlocks,
    }

def run_training_camp_event(context: GameContext):
    # This is a stub or full function depending on if you want it in this file
    # Ideally, keep the implementation I gave in the previous turn here if you want it.
    pass


def _announce_milestones(milestones: List[MilestoneUnlockResult]) -> None:
    if not milestones:
        return
    for entry in milestones:
        label = entry.milestone_label or entry.milestone_key
        print(
            f"{Colour.gold}[MILESTONE]{Colour.RESET} {label}: {entry.description} -> {entry.skill_name}"
        )