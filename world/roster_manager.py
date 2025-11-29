import sqlalchemy
from database.setup_db import School, Player, Coach, Roster, session
from ai.coach_ai.coach_decision import calculate_player_utility

def run_roster_logic(target_school_id=None):
    """
    Main loop. Iterates through schools and sets their 'is_starter' flags
    and populates the 'Roster' table based on Coach AI.
    """
    schools = session.query(School).all()
    if target_school_id:
        schools = [s for s in schools if s.id == target_school_id]
        
    print(f"Running Roster AI for {len(schools)} schools...")
    
    for school in schools:
        update_school_roster(school)
        
    session.commit()
    print("Roster Logic Complete.")

def update_school_roster(school):
    """
    Decides the starting lineup (1-9), Bench (10-18), and Reserves (19+).
    """
    coach = school.coach
    if not coach: return 

    players = school.players
    if not players: return
    
    avg_overall = sum(p.overall for p in players) / len(players)
    
    # 1. Calculate Utility
    player_utilities = []
    for p in players:
        # Injured players automatically drop utility/eligibility
        if getattr(p, 'injury_days', 0) > 0:
            p.is_starter = False
            p.role = "RESERVE"
            p.jersey_number = None
            continue
            
        util = calculate_player_utility(p, coach, avg_overall, session)
        player_utilities.append((p, util))
        
    # Sort ALL players by Utility
    player_utilities.sort(key=lambda x: x[1], reverse=True)
    
    # 2. Reset Roles
    session.query(Roster).filter_by(school_id=school.id).delete()
    assigned_ids = set()
    
    # Helper to pick best available for a position
    def pick_best(pos_list):
        for p_data in pos_list:
            if p_data[0].id not in assigned_ids:
                return p_data[0]
        return None

    # --- STARTERS (The "Nine") ---
    # Pitcher (Ace)
    pitchers = [x for x in player_utilities if x[0].position == "Pitcher"]
    ace = pick_best(pitchers)
    if ace:
        ace.is_starter = True
        ace.role = "ACE"
        ace.jersey_number = 1
        add_to_roster(school.id, "P", ace.id)
        assigned_ids.add(ace.id)

    # Catcher
    catchers = [x for x in player_utilities if x[0].position == "Catcher"]
    starter_c = pick_best(catchers)
    if starter_c:
        starter_c.is_starter = True
        starter_c.role = "STARTER"
        starter_c.jersey_number = 2
        add_to_roster(school.id, "C", starter_c.id)
        assigned_ids.add(starter_c.id)

    # Infielders (1B, 2B, 3B, SS) -> Jerseys 3, 4, 5, 6
    if_positions = [("1B", 3), ("2B", 4), ("3B", 5), ("SS", 6)]
    for pos_name, j_num in if_positions:
        # Try specific fit first, then generic Infielder
        candidates = [x for x in player_utilities if x[0].position == pos_name]
        if not candidates: candidates = [x for x in player_utilities if x[0].position == "Infielder"]
        
        p = pick_best(candidates)
        if p:
            p.is_starter = True
            p.role = "STARTER"
            p.jersey_number = j_num
            add_to_roster(school.id, pos_name, p.id)
            assigned_ids.add(p.id)

    # Outfielders (LF, CF, RF) -> Jerseys 7, 8, 9
    of_positions = [("LF", 7), ("CF", 8), ("RF", 9)]
    for pos_name, j_num in of_positions:
        candidates = [x for x in player_utilities if x[0].position == pos_name]
        if not candidates: candidates = [x for x in player_utilities if x[0].position == "Outfielder"]
        
        p = pick_best(candidates)
        if p:
            p.is_starter = True
            p.role = "STARTER"
            p.jersey_number = j_num
            add_to_roster(school.id, pos_name, p.id)
            assigned_ids.add(p.id)

    # --- BENCH (Jerseys 10-18) ---
    # The next best players regardless of position fill the bench
    bench_slots = 18 - len(assigned_ids)
    
    # Re-sort remaining by utility
    remaining = [x[0] for x in player_utilities if x[0].id not in assigned_ids]
    
    current_jersey = 10
    for i in range(min(len(remaining), bench_slots)):
        p = remaining[i]
        p.is_starter = False
        p.role = "BENCH"
        if p.position == "Pitcher": p.role = "RELIEVER"
        p.jersey_number = current_jersey
        current_jersey += 1
        assigned_ids.add(p.id)

    # --- RESERVES (The rest) ---
    # Everyone else gets role="RESERVE" and no jersey number (or high number)
    reserves = [x[0] for x in player_utilities if x[0].id not in assigned_ids]
    for p in reserves:
        p.is_starter = False
        p.role = "RESERVE"
        p.jersey_number = 99 # Or None, purely cosmetic distinction

def add_to_roster(school_id, pos, player_id):
    r = Roster(school_id=school_id, position=pos, player_id=player_id)
    session.add(r)