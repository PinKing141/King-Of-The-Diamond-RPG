from types import SimpleNamespace
from typing import Callable, List, Optional, Sequence, Tuple

from sqlalchemy.sql.expression import func

from core.config_loader import ConfigLoader
from database.setup_db import School
from core.rng import get_rng
from match_engine.resolver import resolve_match

from .sim_utils import quick_resolve_match

rng = get_rng()

_sim_cfg = ConfigLoader.get("world_sim", default={}) or {}
MAX_BACKGROUND_GAMES = int(_sim_cfg.get("max_background_games", 40))
MAX_PLAYER_BLOCK_GAMES = int(_sim_cfg.get("max_player_block_games", 6))
FEATURE_FOCUS_GAMES = int(_sim_cfg.get("feature_focus_games", 0))
SAMPLE_SIZE_FLOOR = int(_sim_cfg.get("sample_size_floor", 120))


def _pair_schools(schools: Sequence[School], game_count: int) -> List[Tuple[School, School]]:
    pairs: List[Tuple[School, School]] = []
    needed = min(game_count, len(schools) // 2)
    for idx in range(needed):
        pairs.append((schools[idx * 2], schools[idx * 2 + 1]))
    return pairs


def _to_stub(school: School) -> SimpleNamespace:
    return SimpleNamespace(id=getattr(school, "id", None), name=getattr(school, "name", None))


def _simulate_background_matches(
    session,
    user_school_id,
    *,
    feature_games: int = FEATURE_FOCUS_GAMES,
    verbose: bool = False,
    log: Optional[Callable[[str], None]] = None,
):
    feature_pairs: List[Tuple[SimpleNamespace, SimpleNamespace]] = []
    quick_heads = []

    # Build pairings and resolve quick sims using the caller-provided session to avoid spawning new connections.
    sample_size = max(MAX_BACKGROUND_GAMES * 2 + MAX_PLAYER_BLOCK_GAMES * 2, SAMPLE_SIZE_FLOOR)
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

    if verbose and log:
        log(
            f"   > Prefecture world: {len(feature_pairs)} feature games, {len(fast_pairs) + len(quick_pairs)} instant resolves..."
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

    if verbose and log:
        if quick_heads:
            notable = [f"{h} vs {a} ({score})" for h, a, score, upset in quick_heads if upset]
            if notable:
                log(f"   upset radar: {', '.join(notable[:3])}")
        log("   Prefecture background sims complete.")


def simulate_background_matches(
    session,
    user_school_id,
    *,
    background: bool = False,
    feature_games: int = FEATURE_FOCUS_GAMES,
    verbose: bool = False,
    log: Optional[Callable[[str], None]] = None,
) -> Optional[None]:
    """Simulate NPC practice games.

    Uses the caller-provided session (no new connections). Background threading is disabled to avoid
    SQLite locking; this always runs synchronously.
    """

    _simulate_background_matches(
        session,
        user_school_id,
        feature_games=feature_games,
        verbose=verbose,
        log=log,
    )
    return None