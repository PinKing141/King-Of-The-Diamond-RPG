# world_sim/npc_team_ai.py
import random
from database.setup_db import session, School, Player
from world.school_philosophy import get_philosophy

def process_npc_growth(school_id=None):
    """
    Iterates through NPC schools and applies training growth 
    based on their Philosophy.
    """
    query = session.query(School)
    if school_id:
        query = query.filter(School.id == school_id)
        
    schools = query.all()
    # print(f"   > Processing growth for {len(schools)} schools...")

    for school in schools:
        # 1. Get Philosophy Logic
        # Assuming school.philosophy stores the name string, e.g. "Pitching Kingdom"
        phil_name, phil_data = get_philosophy(school.philosophy)
        
        focus = phil_data.get('focus', 'Balanced')
        training_style = phil_data.get('training_style', 'Modern')
        
        # 2. Determine Growth Multipliers
        # Default Growth
        grow_p = 1.0 # Pitching
        grow_b = 1.0 # Batting
        grow_d = 1.0 # Defense
        grow_s = 1.0 # Speed
        
        if focus == "Pitching" or focus == "Ace":
            grow_p = 1.5
        elif focus == "Power" or focus == "Contact":
            grow_b = 1.5
        elif focus == "Defense":
            grow_d = 1.5
        elif focus == "Speed":
            grow_s = 1.5
            
        # 3. Apply to Players
        for p in school.players:
            # Skip maxed players (simplified check)
            if p.overall > 95: continue
            
            # Base growth per week
            base_xp = random.randint(1, 3)
            
            # Apply Multipliers
            if p.position == "Pitcher":
                p.velocity += int(base_xp * grow_p * 0.5)
                p.control += int(base_xp * grow_p * 0.5)
                p.stamina += int(base_xp * grow_p * 0.3)
            else:
                p.contact += int(base_xp * grow_b * 0.5)
                p.power += int(base_xp * grow_b * 0.5)
                p.fielding += int(base_xp * grow_d * 0.5)
                p.speed += int(base_xp * grow_s * 0.5)
                
            # Update Overall (Simple approx)
            if p.position == "Pitcher":
                p.overall = (p.velocity + p.control + p.stamina) // 3
            else:
                p.overall = (p.contact + p.power + p.fielding) // 3
                
    session.commit()