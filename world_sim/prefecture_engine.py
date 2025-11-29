import random
from database.setup_db import session, School, Game
# --- PATCH START ---
from match_engine import sim_match
# --- PATCH END ---

def simulate_background_matches(user_school_id):
    """
    Picks random pairs of NPC schools to play practice matches.
    This keeps the world alive and generates stats.
    """
    # Get all schools except user
    npcs = session.query(School).filter(School.id != user_school_id).all()
    
    if len(npcs) < 2: return

    # Shuffle and pair up
    random.shuffle(npcs)
    
    # Limit number of sim games per week to avoid lag (e.g., 5 games)
    num_games = min(5, len(npcs) // 2)
    
    print(f"   > Simulating {num_games} background matches...")
    
    for i in range(num_games):
        home = npcs[i*2]
        away = npcs[i*2 + 1]
        
        # Run SILENT match
        # Utilizing the Legacy Bridge 'sim_match' which handles silent mode
        winner, score = sim_match(home, away, "Practice Match", silent=True)
        
        # print(f"     [Sim] {home.school_name} vs {away.school_name} -> {winner.school_name} ({score})")