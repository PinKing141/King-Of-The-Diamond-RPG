import threading
from types import SimpleNamespace
from typing import List, Optional, Sequence, Tuple

from database.setup_db import session_scope, School
from match_engine import resolve_match
from game.rng import get_rng

from .sim_utils import quick_resolve_match

rng = get_rng()
MAX_BACKGROUND_GAMES = 40
MAX_PLAYER_BLOCK_GAMES = 6


def _pair_schools(schools: Sequence[School], game_count: int) -> List[Tuple[School, School]]:
    pairs: List[Tuple[School, School]] = []
    needed = min(game_count, len(schools) // 2)
    for idx in range(needed):
        pairs.append((schools[idx * 2], schools[idx * 2 + 1]))
    return pairs


def _to_stub(school: School) -> SimpleNamespace:
    return SimpleNamespace(id=getattr(school, "id", None), name=getattr(school, "name", None))


def _simulate_background_matches(user_school_id):
    with session_scope() as session:
        npc_schools: List[School] = (
            session.query(School).filter(School.id != user_school_id).all()
        )
        if len(npc_schools) < 2:
            return

        user_school = session.get(School, user_school_id)
        user_prefecture = getattr(user_school, "prefecture", None) if user_school else None
        rng.shuffle(npc_schools)
        tier_one = [s for s in npc_schools if user_prefecture and s.prefecture == user_prefecture]
        tier_two = [s for s in npc_schools if s not in tier_one]
        rng.shuffle(tier_one)
        rng.shuffle(tier_two)

        tier_one_pairs = _pair_schools(tier_one, MAX_PLAYER_BLOCK_GAMES)
        used_tier_one = len(tier_one_pairs) * 2
        spillover = tier_one[used_tier_one:]
        remaining_pool = spillover + tier_two
        rng.shuffle(remaining_pool)
        quick_slots = MAX_BACKGROUND_GAMES - len(tier_one_pairs)
        quick_pairs = _pair_schools(remaining_pool, quick_slots)

        print(
            f"   > Prefecture world: {len(tier_one_pairs)} focus games, {len(quick_pairs)} instant resolves...",
            end="",
        )

        quick_heads = []
        for home, away in quick_pairs:
            _, score, upset = quick_resolve_match(session, home, away)
            quick_heads.append((home.name, away.name, score, upset))

        tier_one_stubs = [(_to_stub(home), _to_stub(away)) for home, away in tier_one_pairs]

    for home_stub, away_stub in tier_one_stubs:
        resolve_match(home_stub, away_stub, "Practice Match", mode="fast")

    if quick_heads:
        notable = [f"{h} vs {a} ({score})" for h, a, score, upset in quick_heads if upset]
        if notable:
            print(f" upset radar: {', '.join(notable[:3])}", end="")
    print(" done.")


def simulate_background_matches(user_school_id, *, async_mode: bool = False) -> Optional[threading.Thread]:
    """Simulate NPC practice games; optionally run asynchronously to avoid UI stalls."""

    if async_mode:
        worker = threading.Thread(target=_simulate_background_matches, args=(user_school_id,), daemon=True)
        worker.start()
        return worker

    _simulate_background_matches(user_school_id)
    return None