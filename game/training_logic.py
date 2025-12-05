import json
import logging
import os
import random
from typing import List, Optional, Tuple

from .health_system import check_injury_risk, apply_injury, get_performance_modifiers
from database.setup_db import Player
from game.academic_system import resolve_study_session, clamp, is_academically_eligible
from game.game_context import GameContext
from game.personality_effects import adjust_player_morale, decay_slump
from game.player_progression import (
    MilestoneUnlockResult,
    get_milestone_definitions,
    process_milestone_unlocks,
)
from game.relationship_manager import register_morale_rebound
from game.skill_system import check_and_grant_skills, list_player_skill_keys
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


XP_TRACKED_STATS = {
    'control',
    'velocity',
    'stamina',
    'movement',
    'power',
    'contact',
    'speed',
    'fielding',
    'throwing',
    'command',
}
BREAKTHROUGH_BASE_CHANCE = 0.01
BREAKTHROUGH_SCALE = 0.0004
BREAKTHROUGH_MIN = 0.005
BREAKTHROUGH_MAX = 0.08


def _xp_threshold(stat_value: Optional[float]) -> float:
    value = stat_value or 0.0
    return max(3.0, 3.0 + (value / 20.0))


def _load_training_xp(player: Player) -> dict:
    raw = getattr(player, 'training_xp', None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    cleaned = {}
    for key, value in data.items():
        try:
            cleaned[key] = float(value)
        except (TypeError, ValueError):
            continue
    return cleaned


def _save_training_xp(player: Player, payload: dict) -> None:
    if not payload:
        player.training_xp = '{}'
        return
    # Round stored floats to reduce noise in the save file.
    snapshot = {k: round(v, 4) for k, v in payload.items() if v > 0}
    player.training_xp = json.dumps(snapshot)


def _apply_training_xp(player: Player, xp_gains: dict) -> Tuple[dict, dict]:
    pool = _load_training_xp(player)
    level_ups = {}
    for stat, gain in xp_gains.items():
        current_value = (getattr(player, stat, 0) or 0)
        total_xp = pool.get(stat, 0.0) + gain
        threshold = _xp_threshold(current_value)
        applied_levels = 0
        while total_xp >= threshold:
            total_xp -= threshold
            current_value += 1
            applied_levels += 1
            threshold = _xp_threshold(current_value)
        pool[stat] = total_xp
        if applied_levels:
            setattr(player, stat, current_value)
            level_ups[stat] = applied_levels
    return level_ups, pool


def _maybe_trigger_breakthrough(player: Player, xp_gains: dict, xp_pool: dict) -> Optional[dict]:
    if not xp_gains:
        return None
    determination = getattr(player, 'determination', None)
    if determination is None:
        determination = getattr(player, 'drive', 50) or 50
    chance = BREAKTHROUGH_BASE_CHANCE + max(0.0, determination - 50) * BREAKTHROUGH_SCALE
    chance = max(BREAKTHROUGH_MIN, min(BREAKTHROUGH_MAX, chance))
    roll = random.random()
    if roll > chance:
        return None
    focus_stat = max(xp_gains.items(), key=lambda item: item[1])[0]
    current_value = (getattr(player, focus_stat, 0) or 0) + 1
    setattr(player, focus_stat, current_value)
    xp_pool[focus_stat] = 0.0
    return {
        "stat": focus_stat,
        "new_value": current_value,
        "chance": chance,
        "roll": roll,
    }


def apply_scheduled_action(
    context: GameContext,
    action_type: str,
    *,
    commit: bool = True,
    progression_state: Optional[dict] = None,
) -> dict:
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

    xp_gains: dict = {}
    applied_stat_changes: dict = {}

    for stat, value in stat_gains.items():
        variance = random.uniform(0.9, 1.1)
        final_value = value * variance
        if stat in XP_TRACKED_STATS:
            xp_gains[stat] = xp_gains.get(stat, 0.0) + final_value
        else:
            current = getattr(player, stat, 0) or 0
            setattr(player, stat, current + final_value)
            applied_stat_changes[stat] = applied_stat_changes.get(stat, 0) + final_value

    if 'academic_skill' in stat_gains:
        player.academic_skill = int(round(clamp(player.academic_skill or 0, 25, 110)))
    if 'test_score' in stat_gains:
        player.test_score = int(round(clamp(player.test_score or 0, 0, 100)))

    level_ups: dict = {}
    breakthrough_event: Optional[dict] = None
    if xp_gains:
        level_ups, xp_pool = _apply_training_xp(player, xp_gains)
        breakthrough_event = _maybe_trigger_breakthrough(player, xp_gains, xp_pool)
        _save_training_xp(player, xp_pool)

    if level_ups and PROGRESSION_DEBUG:
        logger.info("Training session yielded level ups: %s", level_ups)
    if breakthrough_event:
        event_text = f"Breakthrough! Your {breakthrough_event['stat'].replace('_', ' ').title()} surges forward."
        summary = f"{summary} {event_text}".strip()

    if level_ups:
        for stat, amount in level_ups.items():
            applied_stat_changes[stat] = applied_stat_changes.get(stat, 0) + amount

    if slump_timer > 0:
        resolved = decay_slump(player)
        if resolved:
            adjust_player_morale(player, 4)
            register_morale_rebound(context.session, player, reason="slump_cleared")
            summary += " (You finally shake the slump.)"

    owned_skill_keys = None
    milestone_defs = None
    milestone_stats_cache = None
    if progression_state is not None:
        owned_skill_keys = progression_state.get("skill_keys")
        if owned_skill_keys is None:
            owned_skill_keys = set(list_player_skill_keys(player))
            progression_state["skill_keys"] = owned_skill_keys
        milestone_defs = progression_state.get("milestone_defs")
        if milestone_defs is None:
            milestone_defs = get_milestone_definitions()
            progression_state["milestone_defs"] = milestone_defs
        milestone_stats_cache = progression_state.setdefault("milestone_stats", {})

    unlocked_skills = check_and_grant_skills(
        context.session,
        player,
        owned_keys=owned_skill_keys,
    )
    milestone_unlocks = process_milestone_unlocks(
        context.session,
        player,
        milestone_definitions=milestone_defs,
        stats_cache=milestone_stats_cache,
        owned_skill_keys=owned_skill_keys,
    )
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
    if commit:
        context.session.commit()
    else:
        context.session.flush()

    return {
        "status": "ok",
        "message": summary,
        "fatigue_change": fatigue_change,
        "stat_changes": applied_stat_changes,
        "xp_gains": xp_gains,
        "breakthrough": breakthrough_event,
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