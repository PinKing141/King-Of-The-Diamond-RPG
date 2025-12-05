import random
import time
from typing import Optional

from database.setup_db import Player, School
from ui.ui_display import Colour
# Import the new Dialogue Manager
from game.dialogue_manager import run_dialogue_event
from game.game_context import GameContext
from game.relationship_manager import (
    seed_relationships,
    adjust_relationship,
    get_rival_pressure_modifier,
    apply_conflict_penalty,
)
from game.coach_strategy import set_strategy_modifier, has_modifier
from game.personality_effects import adjust_player_morale, adjust_team_morale
from game.archetypes import get_player_archetype, get_archetype_profile
from sqlalchemy import func

# --- INSTRUCTIONS FOR ADDING NEW EVENTS ---
# 1. Define your event function (e.g., `event_pizza_party(player, school)`).
#    - It should accept `player` and `school` (and `session` if needed) as arguments.
#    - It should return a string description of what happened.
#    - It should apply changes (e.g., player.morale += 10) directly to the objects.
#
# 2. Add your function to the `EVENT_POOL` list at the bottom of this file.
#    - You can add it multiple times to make it more common.
#    - You can wrap it in a condition check inside `trigger_random_event` if it's situational.
# ------------------------------------------

def event_pop_quiz(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    """Event: Academic pressure using Dialogue System."""
    # We map this event to a specific dialogue ID defined in dialogue_manager.py
    # Ideally, we'd have a specific ID like "teacher_pop_quiz" in the DB.
    # For this example, let's use a generic placeholder or the one we defined.
    
    # Note: If "teacher_pop_quiz" isn't in DIALOGUE_DB yet, this will fail.
    # Let's assume we added "coach_meeting_strategy" in the previous step.
    # Let's use that for demonstration, or add a quick one here if we could.
    
    # Re-using the coach meeting example for now to show functionality
    return run_dialogue_event("coach_meeting_strategy", player, school)

def event_extra_practice(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    """Event: Teammate Interaction."""
    return run_dialogue_event("teammate_practice_extra", player, school)

def event_alumni_donation(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    """Event: School Budget Boost (Simple Text)."""
    donation = random.randint(1000, 5000)
    school.budget += donation
    return f"A wealthy alumnus donated ¥{donation} to the baseball club! (Budget UP)"

def _archetype_label(player) -> str:
    profile = get_archetype_profile(get_player_archetype(player))
    return profile.label


def event_scout_sighting(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    """Event: Motivation Boost."""
    print(f"\n{Colour.YELLOW}[EVENT] SCOUT SPOTTED{Colour.RESET}")
    print("Rumour has it a pro scout is watching practice today.")
    morale_gain = 10
    archetype = get_player_archetype(player)
    if archetype in {"showman", "firebrand"}:
        morale_gain += 6
    elif archetype == "steady":
        morale_gain += 2
    player.morale += morale_gain
    label = _archetype_label(player)
    return f"The team practiced with extra intensity! ({label} aura, Morale +{morale_gain})"

def event_equipment_failure(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    """Event: Minor annoyance."""
    if school.budget >= 500:
        school.budget -= 500
        return "The pitching machine broke. Repairs cost ¥500."
    else:
        player.morale -= 5
        return "The pitching machine broke, and we can't afford repairs. Training was inefficient. (Morale -5)"

def event_love_letter(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    """Event: Classic trope."""
    print(f"\n{Colour.HEADER}[EVENT] SHOE LOCKER SURPRISE{Colour.RESET}")
    print("You found a letter in your shoe locker...")
    
    choice = input("Read it? (y/n): ").lower()
    archetype = get_player_archetype(player)
    if choice == 'y':
        morale = 15
        fatigue = 5
        if archetype == "showman":
            morale += 5
        elif archetype == "strategist":
            fatigue += 2
        player.morale += morale
        player.fatigue += fatigue
        return f"It was a confession! {_archetype_label(player)} vibes rise. (Morale +{morale}, Fatigue +{fatigue})"
    else:
        player.stamina += 1
        if archetype in {"guardian", "steady"}:
            player.morale += 2
        return "You threw it away. BASEBALL IS YOUR ONLY LOVE, staying true to your archetype." 

def event_rival_taunt(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    """Event: Narrative building."""
    return f"Students from a rival school were talking trash at the station. The team is fired up. (Motivation UP)"


def event_coach_strategy_prompt(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    if context is None or school is None or not school.coach:
        return None

    print(f"\n{Colour.HEADER}[MEETING] Coach wants your take on offense.{Colour.RESET}")
    print("Coach: 'Next opponent survives on defense. What's our approach?'")
    print(" 1) Manufacture runs with bunts and pressure")
    print(" 2) Let the lineup swing freely")
    print(" 3) Stick with whatever the staff chooses")

    choice = input("Choice: ").strip()
    if choice not in {'1', '2', '3'}:
        return "You shrug, offering no concrete advice."

    if choice == '3':
        return "You trust the existing plan. Coach nods and ends the chat."

    effect = 'small_ball' if choice == '1' else 'power_focus'
    if has_modifier(context.session, school.id, effect_type=effect):
        return "Coach already has that strategy queued."

    games = random.randint(1, 2)
    set_strategy_modifier(context.session, school.id, effect, games)
    style = "small-ball pressure" if effect == 'small_ball' else "aggressive swings"
    return f"Coach embraces your call. Expect {style} for the next {games} game(s)."


def event_substitution_request(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    if context is None or school is None or not school.coach:
        return None
    if (player.fatigue or 0) < 60:
        return None
    if has_modifier(context.session, school.id, 'rest_player', target_player_id=player.id):
        return None

    print(f"\n{Colour.WARNING}[DECISION] You're gassed after practice.{Colour.RESET}")
    ask = input("Ask coach for a rest day? (y/n): ").strip().lower()
    if ask != 'y':
        return "You grit your teeth and keep quiet."

    coach = school.coach
    base = 0.45
    base += 0.20 * ((coach.logic or 0.5) - 0.5)
    base -= 0.15 * ((coach.tradition or 0.5) - 0.5)
    base += max(0.0, (player.fatigue - 70) / 120)
    base = max(0.05, min(0.9, base))

    granted = random.random() < base
    if granted:
        set_strategy_modifier(
            context.session,
            school.id,
            effect_type='rest_player',
            games=1,
            target_player_id=player.id,
        )
        player.fatigue = max(0, (player.fatigue or 0) - 10)
        context.session.add(player)
        context.session.commit()
        return "Coach agrees: you'll sit the next game to recharge."

    player.discipline = max(20, (player.discipline or 50) - 2)
    context.session.add(player)
    context.session.commit()
    return "Coach refuses, demanding toughness. You steel yourself to push through."


def event_captain_mentorship(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    if context is None:
        return None

    rel = seed_relationships(context.session, player)
    if not rel.captain_id:
        return None
    if current_week and rel.last_captain_event_week == current_week:
        return None

    is_bond_strong = (rel.captain_rel or 0) >= 70
    dialogue_id = "captain_advice_high" if is_bond_strong else "captain_advice_low"
    response = run_dialogue_event(dialogue_id, player, school)

    rel.last_captain_event_week = current_week or rel.last_captain_event_week
    context.session.add(rel)
    adjust_relationship(context.session, rel, 'captain_rel', 3 if is_bond_strong else 1)

    if is_bond_strong:
        context.set_temp_effect('mentor_training', {
            'multiplier': 0.20,
            'source': 'Captain Pep Talk'
        })
        context.session.commit()
        return f"{response} (Captain's advice sharpens your focus. Training gains are boosted this week.)"

    context.session.commit()
    return response


def event_rival_showdown(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    if context is None:
        return None

    rel = seed_relationships(context.session, player)
    if not rel.rival_id:
        return None
    if current_week and rel.last_rival_event_week == current_week:
        return None

    rival = context.session.get(Player, rel.rival_id)
    if not rival:
        return None

    rel.last_rival_event_week = current_week or rel.last_rival_event_week
    context.session.add(rel)
    rivalry_shift = random.choice([-2, -1, 1, 2])
    adjust_relationship(context.session, rel, 'rivalry_score', rivalry_shift)

    pressure = get_rival_pressure_modifier(rel)
    clutch_delta = max(-5, min(5, pressure * 8))
    player.clutch = max(25, min(99, (player.clutch or 50) + clutch_delta))
    context.set_temp_effect('rival_pressure', {
        'clutch_delta': clutch_delta,
        'source': 'Rival Showdown'
    })
    context.session.add(player)
    context.session.commit()

    dialogue_id = "rival_head_to_head" if (rel.rivalry_score or 45) >= 55 else "rival_mind_games"
    summary = run_dialogue_event(dialogue_id, player, school)
    delta_text = f"Clutch {'+' if clutch_delta >= 0 else ''}{int(round(clutch_delta))}" if clutch_delta else "Focused"
    return f"{summary} ({delta_text} heading into the next matchup.)"


def event_training_conflict(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    if context is None or school is None:
        return None
    volatility = getattr(player, 'volatility', 50) or 50
    archetype = get_player_archetype(player)
    trigger = 0.35
    if archetype == "firebrand":
        trigger += 0.2
    elif archetype in {"guardian", "steady"}:
        trigger -= 0.15
    if volatility < 65 or random.random() > trigger:
        return None

    teammate = (
        context.session.query(Player)
        .filter(Player.school_id == school.id, Player.id != player.id)
        .order_by(func.random())
        .first()
    )
    if not teammate:
        return None

    adjust_player_morale(player, -6)
    adjust_player_morale(teammate, -4)
    adjust_team_morale(context.session, school.id, -2, exclude_ids=[player.id, teammate.id])
    apply_conflict_penalty(context.session, [player, teammate], severity="minor")
    context.session.add_all([player, teammate])
    context.session.commit()

    return (
        f"Practice derails when {player.name}—a {_archetype_label(player)}—and {teammate.name} start shouting matches. "
        "Coach ends the session early, and the locker room mood dips."
    )


def event_volatility_fight(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    if context is None or school is None:
        return None

    hotheads = context.session.query(Player).filter(
        Player.school_id == school.id,
        Player.volatility >= 70,
    ).all()
    if len(hotheads) < 2 or random.random() > 0.18:
        return None

    instigator, target = random.sample(hotheads, 2)
    adjust_player_morale(instigator, -8)
    adjust_player_morale(target, -8)
    adjust_team_morale(context.session, school.id, -4, exclude_ids=[instigator.id, target.id])

    mediator = None
    hero = context.session.get(Player, context.player_id) if context.player_id else None
    if hero and (hero.loyalty or 50) >= 65:
        mediator = hero
    else:
        captain = context.session.query(Player).filter(
            Player.school_id == school.id,
            Player.is_captain == True,
        ).first()
        if captain and (captain.loyalty or 50) >= 65:
            mediator = captain

    rel_inst = seed_relationships(context.session, instigator)
    rel_target = seed_relationships(context.session, target)
    rel_inst.rival_id = rel_inst.rival_id or target.id
    rel_target.rival_id = rel_target.rival_id or instigator.id
    adjust_relationship(context.session, rel_inst, 'rivalry_score', random.randint(4, 8))
    adjust_relationship(context.session, rel_target, 'rivalry_score', random.randint(4, 8))
    apply_conflict_penalty(context.session, [instigator, target], severity="major")

    summary = (
        f"Tempers explode between {instigator.name} and {target.name}. "
        "Both players lose the coach's trust, and teammates whisper all afternoon."
    )

    if mediator:
        adjust_player_morale(mediator, 3)
        summary += f" {mediator.name} steps in to cool everyone down, preventing suspensions."
    else:
        summary += " No one intervenes, and the feud simmers heading into the next game."

    context.session.add_all([instigator, target, rel_inst, rel_target])
    context.session.commit()
    return summary


def event_shrine_visit(player, school, context: Optional[GameContext] = None, current_week: Optional[int] = None):
    """Traditional team visit to a local shrine for blessings before a big stretch."""

    if context is None or school is None:
        return None
    if random.random() > 0.55:
        return None

    print(f"\n{Colour.HEADER}[RITUAL] Shrine bells echo in the morning mist.{Colour.RESET}")
    loyalty = getattr(player, 'loyalty', 50) or 50
    offering = random.randint(300, 800)
    paid = False
    if school.budget >= offering:
        school.budget -= offering
        paid = True

    fortune_roll = random.random() + (loyalty - 50) / 120
    summary = "The club lines up, claps twice, and bows beneath the cedar torii."

    archetype = get_player_archetype(player)
    if archetype in {"guardian", "steady"}:
        fortune_roll += 0.08
    if fortune_roll >= 0.85:
        adjust_player_morale(player, 8)
        adjust_team_morale(context.session, school.id, 4)
        player.discipline = min(99, (player.discipline or 55) + 3)
        player.fatigue = max(0, (player.fatigue or 0) - 8)
        blessing = f"A rare omikuji blessing promises tournament fortune. The {_archetype_label(player)} offers guidance."
    elif fortune_roll >= 0.45:
        adjust_player_morale(player, 4)
        adjust_team_morale(context.session, school.id, 2)
        player.discipline = min(99, (player.discipline or 55) + 1)
        player.fatigue = max(0, (player.fatigue or 0) - 3)
        blessing = "The miko nods approvingly—good focus breeds good baseball."
    else:
        adjust_player_morale(player, -2)
        player.discipline = min(99, (player.discipline or 55) + 2)
        blessing = "An ominous fortune warns against arrogance; the team doubles down on fundamentals."

    context.session.add(player)
    context.session.add(school)
    context.session.commit()

    budget_line = f" The club offers ¥{offering} in ema wishes." if paid else " Funds are tight, but the team scrapes together coins for the prayer box."
    return f"{summary}{budget_line} {blessing}"

# --- MAIN EVENT CONTROLLER ---

EVENT_POOL = [
    event_pop_quiz,
    event_extra_practice,
    event_alumni_donation,
    event_scout_sighting,
    event_equipment_failure,
    event_love_letter,
    event_rival_taunt,
    event_coach_strategy_prompt,
    event_substitution_request,
    event_captain_mentorship,
    event_rival_showdown,
    event_training_conflict,
    event_volatility_fight,
    event_shrine_visit,
]

def trigger_random_event(context: Optional[GameContext] = None, current_week: Optional[int] = None):
    """
    Called weekly. Decides if an event happens, picks one, runs it, and saves changes.
    """
    if random.random() > 0.40: # 40% chance
        return 

    if context is None or context.player_id is None:
        return

    session = context.session

    player = session.get(Player, context.player_id)
    school = session.get(School, player.school_id) if player else None
    
    if not player or not school:
        return

    # Pick Random Event
    event_func = random.choice(EVENT_POOL)
    
    # Execute Logic
    result_text = event_func(player, school, context, current_week)
    
    # Commit changes
    session.commit()
    
    # Display Result
    if result_text and not result_text.startswith("Dialogue"):
        print(f"\n{Colour.BOLD}>> WEEKLY HIGHLIGHT: {result_text}{Colour.RESET}")
        time.sleep(1.5)
    
    # Session lifecycle managed by caller/context
    return result_text