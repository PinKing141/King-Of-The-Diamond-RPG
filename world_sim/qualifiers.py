import random
import math
import time
from sqlalchemy.orm import sessionmaker
from database.setup_db import School, engine
from match_engine import sim_match
from ui.ui_display import Colour

Session = sessionmaker(bind=engine)
session = Session()

def generate_balanced_bracket(schools):
    """
    Organizes schools into a standard single-elimination bracket.
    Handles byes by giving them to top prestige schools.
    """
    n = len(schools)
    if n < 2: return schools # No bracket needed
    
    # Next power of 2 (e.g., if 6 teams, need 8 slots)
    power_of_2 = 2**math.ceil(math.log2(n))
    byes = power_of_2 - n
    
    # Sort by Prestige (Top seeds get byes)
    sorted_schools = sorted(schools, key=lambda s: s.prestige, reverse=True)
    
    # The top 'byes' schools advance automatically to Round 2
    advanced_schools = sorted_schools[:byes]
    first_round_schools = sorted_schools[byes:]
    
    # Shuffle first round matchups for randomness
    random.shuffle(first_round_schools)
    
    return first_round_schools, advanced_schools

def run_district_tournament(district_name, user_school_id):
    """
    Runs a full qualifier tournament for a specific district.
    Returns the Winning School.
    """
    # 1. Get Schools in District
    schools = session.query(School).filter_by(prefecture=district_name).all()
    
    if len(schools) < 2:
        return schools[0] if schools else None
        
    print(f"\n{Colour.CYAN}--- {district_name.upper()} QUALIFIERS ({len(schools)} Schools) ---{Colour.RESET}")
    
    # 2. Bracket Generation
    current_round, bye_teams = generate_balanced_bracket(schools)
    round_num = 1
    
    # If we have teams playing in Round 1
    while len(current_round) > 1 or (len(current_round) == 0 and len(bye_teams) > 1):
        
        # Merge byes back in for Round 2+
        if round_num == 2:
            current_round.extend(bye_teams)
            random.shuffle(current_round)
            bye_teams = []
            
        next_round = []
        
        # Pair up
        matchups = []
        for i in range(0, len(current_round), 2):
            if i+1 < len(current_round):
                matchups.append((current_round[i], current_round[i+1]))
            else:
                # Odd number logic (shouldn't happen with power of 2 logic, but safety)
                next_round.append(current_round[i])

        if not matchups and len(next_round) == 1 and round_num > 1:
             # Winner found
             break

        # print(f" > Round {round_num}: {len(matchups)} Matches")
        
        for home, away in matchups:
            # Check if User is involved
            is_user_match = (home.id == user_school_id or away.id == user_school_id)
            
            if is_user_match:
                print(f"\n{Colour.GREEN}*** QUALIFIER MATCH: {home.name} vs {away.name} ***{Colour.RESET}")
                input("   Press Enter to play...")
                winner, score = sim_match(home, away, f"{district_name} Round {round_num}", silent=False)
                
                if winner.id != user_school_id:
                    print(f"{Colour.FAIL}   ELIMINATED! You lost {score}.{Colour.RESET}")
                    # In a real game, you'd stop the flow here or watch the rest
                else:
                    print(f"{Colour.gold}   VICTORY! Score: {score}{Colour.RESET}")
            else:
                # Background Sim
                winner, score = sim_match(home, away, f"{district_name} Round {round_num}", silent=True)
            
            next_round.append(winner)
            
        current_round = next_round
        round_num += 1
        
    champion = current_round[0]
    # print(f"   🏆 {district_name} Winner: {champion.name}")
    return champion

def run_season_qualifiers(user_school_id):
    """
    Runs qualifiers for EVERY district in Japan to determine Koshien participants.
    Returns a list of School objects (The 49 Representatives).
    """
    # 1. Distinct Districts
    # V2 schema uses 'prefecture' column. 
    prefectures = [r[0] for r in session.query(School.prefecture).distinct()]
    
    koshien_reps = []
    
    print(f"\n{Colour.HEADER}=== SUMMER KOSHIEN QUALIFIERS BEGIN ==={Colour.RESET}")
    print(f"Districts to simulate: {len(prefectures)}")
    time.sleep(1)
    
    for pref in prefectures:
        # Check if User is in this prefecture
        user_school = session.query(School).get(user_school_id)
        is_user_pref = (user_school.prefecture == pref)
        
        if is_user_pref:
            # Run Detailed Simulation
            champ = run_district_tournament(pref, user_school_id)
        else:
            # Run Fast Simulation (Silent)
            # Optimization: Just pick a random winner weighted by prestige?
            # Or run actual sim if CPU power allows. 
            # For 49 districts x 20 teams, full sim might take 10-20 seconds.
            # Let's run full sim for realism but silent.
            champ = run_district_tournament(pref, -1) # -1 ID ensures silent
            
        koshien_reps.append(champ)
        
    print(f"\n{Colour.gold}QUALIFIERS COMPLETE. 49 SCHOOLS ADVANCE.{Colour.RESET}")
    return koshien_reps