import random
import time
from sqlalchemy.orm import sessionmaker
from database.setup_db import engine, Player, School
from ui.ui_display import Colour, clear_screen
from utils import PLAYER_ID
# Import the new Dialogue Manager
from game.dialogue_manager import run_dialogue_event

Session = sessionmaker(bind=engine)

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

def event_pop_quiz(player, school):
    """Event: Academic pressure using Dialogue System."""
    # We map this event to a specific dialogue ID defined in dialogue_manager.py
    # Ideally, we'd have a specific ID like "teacher_pop_quiz" in the DB.
    # For this example, let's use a generic placeholder or the one we defined.
    
    # Note: If "teacher_pop_quiz" isn't in DIALOGUE_DB yet, this will fail.
    # Let's assume we added "coach_meeting_strategy" in the previous step.
    # Let's use that for demonstration, or add a quick one here if we could.
    
    # Re-using the coach meeting example for now to show functionality
    return run_dialogue_event("coach_meeting_strategy", player, school)

def event_extra_practice(player, school):
    """Event: Teammate Interaction."""
    return run_dialogue_event("teammate_practice_extra", player, school)

def event_alumni_donation(player, school):
    """Event: School Budget Boost (Simple Text)."""
    donation = random.randint(1000, 5000)
    school.budget += donation
    return f"A wealthy alumnus donated ¥{donation} to the baseball club! (Budget UP)"

def event_scout_sighting(player, school):
    """Event: Motivation Boost."""
    print(f"\n{Colour.YELLOW}[EVENT] SCOUT SPOTTED{Colour.RESET}")
    print("Rumour has it a pro scout is watching practice today.")
    player.morale += 10
    return "The team practiced with extra intensity! (Morale +10)"

def event_equipment_failure(player, school):
    """Event: Minor annoyance."""
    if school.budget >= 500:
        school.budget -= 500
        return "The pitching machine broke. Repairs cost ¥500."
    else:
        player.morale -= 5
        return "The pitching machine broke, and we can't afford repairs. Training was inefficient. (Morale -5)"

def event_love_letter(player, school):
    """Event: Classic trope."""
    print(f"\n{Colour.HEADER}[EVENT] SHOE LOCKER SURPRISE{Colour.RESET}")
    print("You found a letter in your shoe locker...")
    
    choice = input("Read it? (y/n): ").lower()
    if choice == 'y':
        player.morale += 15
        player.fatigue += 5 
        return "It was a confession! You're walking on air, but distracted. (Morale +15, Fatigue +5)"
    else:
        player.stamina += 1 
        return "You threw it away. BASEBALL IS YOUR ONLY LOVE. (Guts/Stamina slightly UP)"

def event_rival_taunt(player, school):
    """Event: Narrative building."""
    return f"Students from a rival school were talking trash at the station. The team is fired up. (Motivation UP)"

# --- MAIN EVENT CONTROLLER ---

EVENT_POOL = [
    event_pop_quiz, # Uses Dialogue
    event_extra_practice, # Uses Dialogue
    event_alumni_donation,
    event_scout_sighting,
    event_equipment_failure,
    event_love_letter,
    event_rival_taunt,
]

def trigger_random_event():
    """
    Called weekly. Decides if an event happens, picks one, runs it, and saves changes.
    """
    if random.random() > 0.40: # 40% chance
        return 

    session = Session()
    player = session.query(Player).get(PLAYER_ID)
    school = session.query(School).get(player.school_id)
    
    if not player or not school:
        session.close()
        return

    # Pick Random Event
    event_func = random.choice(EVENT_POOL)
    
    # Execute Logic
    result_text = event_func(player, school)
    
    # Commit changes
    session.commit()
    
    # Display Result
    if result_text and not result_text.startswith("Dialogue"):
        print(f"\n{Colour.BOLD}>> WEEKLY HIGHLIGHT: {result_text}{Colour.RESET}")
        time.sleep(1.5)
        
    session.close()