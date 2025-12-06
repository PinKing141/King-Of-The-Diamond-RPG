import threading
from types import SimpleNamespace
from typing import List, Optional, Sequence, Tuple

from sqlalchemy.sql.expression import func

from database.setup_db import session_scope, School
from game.rng import get_rng
from match_engine import resolve_match

from .sim_utils import quick_resolve_match

rng = get_rng()
MAX_BACKGROUND_GAMES = 40
MAX_PLAYER_BLOCK_GAMES = 6
FEATURE_FOCUS_GAMES = 0


def _pair_schools(schools: Sequence[School], game_count: int) -> List[Tuple[School, School]]:
    pairs: List[Tuple[School, School]] = []
    needed = min(game_count, len(schools) // 2)
    for idx in range(needed):
        pairs.append((schools[idx * 2], schools[idx * 2 + 1]))
    return pairs


def _to_stub(school: School) -> SimpleNamespace:
    return SimpleNamespace(id=getattr(school, "id", None), name=getattr(school, "name", None))


def _simulate_background_matches(user_school_id, *, feature_games: int = FEATURE_FOCUS_GAMES):
    feature_pairs: List[Tuple[SimpleNamespace, SimpleNamespace]] = []
    quick_heads = []

    # Build pairings and resolve quick sims inside a single DB session, then close it before feature games.
    with session_scope() as session:
        sample_size = max(MAX_BACKGROUND_GAMES * 2 + MAX_PLAYER_BLOCK_GAMES * 2, 120)
        npc_schools: List[School] = (
            session.query(School)
            .filter(School.id != user_school_id)
            .order_by(func.random())
            .limit(sample_size)
            .all()
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
        focus_count = max(0, min(len(tier_one_pairs), feature_games))
        feature_pairs = [(_to_stub(h), _to_stub(a)) for h, a in tier_one_pairs[:focus_count]]
        fast_pairs = tier_one_pairs[focus_count:]
        used_tier_one = len(tier_one_pairs) * 2
        spillover = tier_one[used_tier_one:]
        remaining_pool = spillover + tier_two
        rng.shuffle(remaining_pool)
        quick_slots = MAX_BACKGROUND_GAMES - len(tier_one_pairs)
        quick_pairs = _pair_schools(remaining_pool, quick_slots)

        print(
            f"   > Prefecture world: {len(feature_pairs)} feature games, {len(fast_pairs) + len(quick_pairs)} instant resolves...",
            end="",
        )

        # Resolve non-feature games via the fast statistical path to avoid heavy match engine costs.
        for home, away in (*fast_pairs, *quick_pairs):
            _, score, upset = quick_resolve_match(session, home, away)
            quick_heads.append((home.name, away.name, score, upset))

    # Run feature games after the sampling session closes to avoid DB locks during the full engine.
    for home, away in feature_pairs:
        resolve_match(
            home,
            away,
            tournament_name="Prefecture Scrimmage",
            mode="fast",
            persist_results=False,
        )

    if quick_heads:
        notable = [f"{h} vs {a} ({score})" for h, a, score, upset in quick_heads if upset]
        if notable:
            print(f" upset radar: {', '.join(notable[:3])}", end="")
    print(" done.")


def simulate_background_matches(
    user_school_id,
    *,
    async_mode: bool = False,
    feature_games: int = FEATURE_FOCUS_GAMES,
) -> Optional[threading.Thread]:
    """Simulate NPC practice games; optionally run asynchronously to avoid UI stalls."""

    if async_mode:
        worker = threading.Thread(
            target=_simulate_background_matches,
            args=(user_school_id,),
            kwargs={"feature_games": feature_games},
            daemon=True,
        )
        worker.start()
        return worker

    _simulate_background_matches(user_school_id, feature_games=feature_games)
    return None