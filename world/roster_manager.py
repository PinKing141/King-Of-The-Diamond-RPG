from collections import defaultdict

from database.setup_db import School, Player, Coach, Roster, get_session
from game.academic_system import is_academically_eligible
from game.coach_strategy import get_resting_player_ids
from ai.coach_ai.coach_decision import calculate_player_utility

INFIELD_POSITIONS = {"1B", "2B", "3B", "SS", "Infielder"}
OUTFIELD_POSITIONS = {"LF", "CF", "RF", "Outfielder"}

def run_roster_logic(target_school_id=None, db_session=None):
    """
    Main loop. Iterates through schools and sets their 'is_starter' flags
    and populates the 'Roster' table based on Coach AI.
    """
    close_session = False
    if db_session is None:
        db_session = get_session()
        close_session = True

    schools = db_session.query(School).all()
    if target_school_id:
        schools = [s for s in schools if s.id == target_school_id]
        
    print(f"Running Roster AI for {len(schools)} schools...")
    
    for school in schools:
        update_school_roster(db_session, school)
        
    db_session.commit()
    print("Roster Logic Complete.")

    if close_session:
        db_session.close()

def update_school_roster(db_session, school):
    """
    Decides the starting lineup (1-9), Bench (10-18), and Reserves (19+).
    """
    coach = school.coach
    if not coach: return 

    players = school.players
    if not players: return
    resting_ids = set(get_resting_player_ids(db_session, school.id))
    
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

        if not is_academically_eligible(p, school):
            p.is_starter = False
            p.role = "ACADEMIC HOLD"
            p.jersey_number = None
            continue

        if p.id in resting_ids:
            p.is_starter = False
            p.role = "RESTING"
            p.jersey_number = None
            continue
            
        util = calculate_player_utility(p, coach, avg_overall, db_session)
        player_utilities.append((p, util))
        
    # Sort ALL players by Utility
    player_utilities.sort(key=lambda x: x[1], reverse=True)
    
    # 2. Reset Roles
    db_session.query(Roster).filter_by(school_id=school.id).delete()
    usage_counts = defaultdict(int)

    def max_slots(player):
        if getattr(player, "is_two_way", False) and getattr(player, "secondary_position", None):
            return 2
        return 1

    def can_use(player):
        return usage_counts[player.id] < max_slots(player)

    def matches_position(player, slot):
        slot_norm = normalize_slot(slot)
        return _label_matches(player.position, slot_norm) or (
            getattr(player, "secondary_position", None) and _label_matches(player.secondary_position, slot_norm)
        )

    def find_player(slot, fallback=None):
        for p, _ in player_utilities:
            if not matches_position(p, slot):
                continue
            if can_use(p):
                return p
        if fallback:
            for p, _ in player_utilities:
                if not matches_position(p, fallback):
                    continue
                if can_use(p):
                    return p
        return None

    def assign_player(player, roster_slot, jersey, primary_role):
        if not player or not can_use(player):
            return False
        first_assignment = usage_counts[player.id] == 0
        usage_counts[player.id] += 1
        add_to_roster(db_session, school.id, roster_slot, player.id)

        player.is_starter = True
        if first_assignment:
            player.role = primary_role
            player.jersey_number = jersey
        return True

    # --- STARTERS (The "Nine") ---
    # Pitcher (Ace)
    ace = find_player("Pitcher")
    if ace:
        assign_player(ace, "P", 1, "ACE")

    # Catcher
    starter_c = find_player("Catcher")
    if starter_c:
        assign_player(starter_c, "C", 2, "STARTER")

    # Infielders (1B, 2B, 3B, SS) -> Jerseys 3, 4, 5, 6
    if_positions = [("1B", 3), ("2B", 4), ("3B", 5), ("SS", 6)]
    for pos_name, j_num in if_positions:
        p = find_player(pos_name, fallback="Infielder")
        if p:
            assign_player(p, pos_name, j_num, "STARTER")

    # Outfielders (LF, CF, RF) -> Jerseys 7, 8, 9
    of_positions = [("LF", 7), ("CF", 8), ("RF", 9)]
    for pos_name, j_num in of_positions:
        p = find_player(pos_name, fallback="Outfielder")
        if p:
            assign_player(p, pos_name, j_num, "STARTER")

    # --- BENCH (Jerseys 10-18) ---
    # The next best players regardless of position fill the bench
    starter_ids = {pid for pid, count in usage_counts.items() if count > 0}
    bench_slots = 18 - len(starter_ids)
    
    # Re-sort remaining by utility
    remaining = [x[0] for x in player_utilities if x[0].id not in starter_ids]
    
    current_jersey = 10
    for i in range(min(len(remaining), bench_slots)):
        p = remaining[i]
        p.is_starter = False
        p.role = "BENCH"
        if p.position == "Pitcher": p.role = "RELIEVER"
        p.jersey_number = current_jersey
        current_jersey += 1
        starter_ids.add(p.id)

    # --- RESERVES (The rest) ---
    # Everyone else gets role="RESERVE" and no jersey number (or high number)
    reserves = [x[0] for x in player_utilities if x[0].id not in starter_ids]
    for p in reserves:
        p.is_starter = False
        p.role = "RESERVE"
        p.jersey_number = 99 # Or None, purely cosmetic distinction

def add_to_roster(db_session, school_id, pos, player_id):
    r = Roster(school_id=school_id, position=pos, player_id=player_id)
    db_session.add(r)


def normalize_slot(slot):
    if slot == "P":
        return "Pitcher"
    if slot == "C":
        return "Catcher"
    return slot


def _label_matches(label, slot):
    if not label:
        return False
    if label == slot:
        return True

    if label == "Infielder" and slot in INFIELD_POSITIONS:
        return True
    if label in INFIELD_POSITIONS and slot == "Infielder":
        return True

    if label == "Outfielder" and slot in OUTFIELD_POSITIONS:
        return True
    if label in OUTFIELD_POSITIONS and slot == "Outfielder":
        return True

    if label == "Pitcher" and slot == "P":
        return True
    if label == "Catcher" and slot == "C":
        return True

    return False