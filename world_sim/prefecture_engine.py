from database.setup_db import session_scope, School
# --- PATCH START ---
from match_engine import sim_match_fast
# --- PATCH END ---
from game.rng import get_rng

rng = get_rng()

def simulate_background_matches(user_school_id):
    """
    Picks random pairs of NPC schools to play practice matches.
    This keeps the world alive and generates stats.
    """
    # Get all schools except user
    with session_scope() as session:
        npcs = session.query(School).filter(School.id != user_school_id).all()
    
    if len(npcs) < 2: return

    # Shuffle and pair up
    rng.shuffle(npcs)
    
    # Limit number of sim games per week to avoid lag (e.g., 5 games)
    num_games = min(5, len(npcs) // 2)
    
    print(f"   > Simulating {num_games} background matches...")
    
    for i in range(num_games):
        home = npcs[i*2]
        away = npcs[i*2 + 1]
        
        # Run fast background match with no commentary
        winner, score = sim_match_fast(home, away, "Practice Match")
        
        # print(f"     [Sim] {home.school_name} vs {away.school_name} -> {winner.school_name} ({score})")