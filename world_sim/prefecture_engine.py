from types import SimpleNamespace

from database.setup_db import session_scope, School
from match_engine import sim_match_fast
from game.rng import get_rng

rng = get_rng()
MAX_BACKGROUND_GAMES = 40

def simulate_background_matches(user_school_id):
    """
    Picks random pairs of NPC schools to play practice matches.
    This keeps the world alive and generates stats.
    """
    with session_scope() as session:
        npc_ids = [row[0] for row in session.query(School.id).filter(School.id != user_school_id)]

    if len(npc_ids) < 2:
        return

    rng.shuffle(npc_ids)
    num_games = min(MAX_BACKGROUND_GAMES, len(npc_ids) // 2)
    if num_games == 0:
        return

    placeholders = [SimpleNamespace(id=sid) for sid in npc_ids[: num_games * 2]]
    print(f"   > Simulating {num_games} background matches...", end="")

    for i in range(num_games):
        home = placeholders[i * 2]
        away = placeholders[i * 2 + 1]
        sim_match_fast(home, away, "Practice Match")

    print(" done.")