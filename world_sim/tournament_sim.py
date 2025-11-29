# world_sim/tournament_sim.py
import random
import time
from database.setup_db import session, School
from match_engine import sim_match
from ui.ui_display import Colour, clear_screen

def run_koshien_tournament(user_school_id, participants=None):
    """
    Summer Koshien: 49 Teams (Qualifiers Winners).
    """
    _run_generic_tournament("SUMMER KOSHIEN", user_school_id, participants)

def run_spring_koshien(user_school_id):
    """
    Spring Koshien (Senbatsu): 32 Teams (Invitational).
    Selection is based on Prestige and Fall Performance (Simulated by Prestige here).
    """
    clear_screen()
    print(f"{Colour.HEADER}=== SPRING SENBATSU (INVITATIONAL) SELECTION ==={Colour.RESET}\n")
    time.sleep(1)
    
    # 1. Select Top 32 Schools by Prestige
    # We exclude the user school initially to see if they make the cut naturally
    all_schools = session.query(School).order_by(School.prestige.desc()).all()
    
    # The cut-off line
    participants = all_schools[:32]
    
    # Check if user made it
    user_school = session.query(School).get(user_school_id)
    user_qualified = user_school in participants
    
    if user_qualified:
        print(f"{Colour.gold}INVITATION RECEIVED!{Colour.RESET}")
        print(f"The committee has selected {user_school.name} for the Spring Tournament.")
    else:
        print(f"{Colour.FAIL}No invitation received.{Colour.RESET}")
        print(f"Your prestige ({user_school.prestige}) was not high enough to impress the committee.")
        print("You watch the Spring tournament from home...")
    
    input("Press Enter to continue...")
    
    # Run the bracket
    _run_generic_tournament("SPRING SENBATSU", user_school_id, participants)

def _run_generic_tournament(title, user_school_id, participants):
    """
    Shared logic for running any bracket.
    """
    clear_screen()
    print(f"{Colour.HEADER}=== {title} BEGINS ==={Colour.RESET}\n")
    
    user_school = session.query(School).get(user_school_id)
    
    if not participants:
        # Fallback if None passed
        npcs = session.query(School).filter(School.id != user_school_id).all()
        participants = random.sample(npcs, 15)
        participants.append(user_school)
        
    current_bracket = list(participants) # Copy
    random.shuffle(current_bracket)
    
    # Trim to power of 2
    if len(current_bracket) > 32: current_bracket = current_bracket[:32]
    elif len(current_bracket) > 16: current_bracket = current_bracket[:16]
        
    round_num = 1
    
    while len(current_bracket) > 1:
        next_round = []
        print(f"\n{Colour.CYAN}--- ROUND {round_num} ({len(current_bracket)} Teams) ---{Colour.RESET}")
        time.sleep(1)
        
        matchups = []
        for i in range(0, len(current_bracket), 2):
            if i+1 < len(current_bracket):
                matchups.append((current_bracket[i], current_bracket[i+1]))
            
        for home, away in matchups:
            is_user_match = (home.id == user_school_id or away.id == user_school_id)
            
            print(f" > Match: {home.name} vs {away.name}")
            
            winner = None
            score = ""
            
            if is_user_match:
                print(f"{Colour.GREEN}   *** YOUR MATCH ***{Colour.RESET}")
                input("   Press Enter to take the field...")
                winner, score = sim_match(home, away, f"{title} Round {round_num}", silent=False)
            else:
                winner, score = sim_match(home, away, f"{title} Round {round_num}", silent=True)
                print(f"   Result: {winner.name} wins! ({score})")
                time.sleep(0.1)
            
            next_round.append(winner)
            
            if is_user_match and winner.id != user_school_id:
                print(f"\n{Colour.FAIL}You have been eliminated.{Colour.RESET}")
                input("Press Enter...")
                return 
                
        current_bracket = next_round
        round_num += 1
        
    winner = current_bracket[0]
    
    if winner.id == user_school_id:
        print(f"\n{Colour.gold}🏆 CONGRATULATIONS! YOU WON {title}! 🏆{Colour.RESET}")
        user_school.prestige += 15
        session.commit()
    else:
        print(f"\nWinner: {winner.name}")