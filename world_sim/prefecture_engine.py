import logging
from types import SimpleNamespace
from typing import Callable, List, Optional, Sequence, Tuple

from core.config_loader import ConfigLoader
from core.io_interface import IOInterface
from database.setup_db import School
from core.rng import get_rng
from match_engine.resolver import resolve_match
from world_sim.services.sim_data import get_strength_map
from world_sim.services.sim_logging import log_event
from world_sim.sim_utils import clear_strength_cache
from world_sim.strength_cache import strength_cache_scope

from .sim_utils import quick_resolve_match

rng = get_rng()
LOG = logging.getLogger(__name__)

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
    io: IOInterface | None = None,
    event_listeners: Optional[Sequence] = None,
):
    with strength_cache_scope() as cache:
        feature_pairs: List[Tuple[SimpleNamespace, SimpleNamespace]] = []
        quick_heads = []

        # Build pairings and resolve quick sims using the caller-provided session to avoid spawning new connections.
        clear_strength_cache(cache)
        sample_size = max(MAX_BACKGROUND_GAMES * 2 + MAX_PLAYER_BLOCK_GAMES * 2, SAMPLE_SIZE_FLOOR)
        base_query = session.query(School.id).filter(School.id != user_school_id)
        total = base_query.count()
        if total < 2:
            return

        target = min(sample_size, total)
        seen_ids = set()
        max_attempts = target * 3
        attempts = 0
        while len(seen_ids) < target and attempts < max_attempts:
            offset = rng.randint(0, total - 1)
            row = base_query.order_by(School.id).offset(offset).limit(1).first()
            if row and getattr(row, "id", None) is not None:
                seen_ids.add(row.id)
            attempts += 1

        if len(seen_ids) < target:
            # Fallback to grabbing the first N if random sampling underfilled.
            rows = base_query.order_by(School.id).limit(target).all()
            seen_ids.update(getattr(r, "id", None) for r in rows if getattr(r, "id", None) is not None)

        npc_schools: List[School] = (
            session.query(School)
            .filter(School.id.in_(list(seen_ids)))
            .all()
        )
        if len(npc_schools) < 2:
            return

        strength_map = get_strength_map(
            session,
            school_ids=[sid for s in npc_schools if (sid := getattr(s, "id", None)) is not None],
            cache=cache,
        )

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

        logger = log or (io.log if io else LOG.info)

        if verbose and logger:
            logger(
                f"   > Prefecture world: {len(feature_pairs)} feature games, {len(fast_pairs) + len(quick_pairs)} instant resolves..."
            )
        log_event(
            "prefecture_background_start",
            feature_games=len(feature_pairs),
            quick_games=len(fast_pairs) + len(quick_pairs),
            user_school_id=user_school_id,
        )

        # Resolve non-feature games via the fast statistical path to avoid heavy match engine costs.
        for home, away in (*fast_pairs, *quick_pairs):
            _, score, upset, *_ids = quick_resolve_match(session, home, away, strength_map=strength_map, cache=cache)
            quick_heads.append((home.name, away.name, score, upset))
            if upset:
                log_event(
                    "prefecture_background_upset",
                    home_id=getattr(home, "id", None),
                    away_id=getattr(away, "id", None),
                    score=score,
                    user_prefecture=user_prefecture,
                )

    # Run feature games after the sampling session closes to avoid DB locks during the full engine.
    for home, away in feature_pairs:
        resolve_match(
            home,
            away,
            tournament_name="Prefecture Scrimmage",
            mode="fast",
            persist_results=False,
            session=session,
            event_listeners=event_listeners,
        )

    if verbose and logger:
        if quick_heads:
            notable = [f"{h} vs {a} ({score})" for h, a, score, upset in quick_heads if upset]
            if notable:
                logger(f"   upset radar: {', '.join(notable[:3])}")
        logger("   Prefecture background sims complete.")
    log_event(
        "prefecture_background_complete",
        total_games=len(fast_pairs) + len(quick_pairs) + len(feature_pairs),
        feature_games=len(feature_pairs),
        quick_games=len(fast_pairs) + len(quick_pairs),
        user_school_id=user_school_id,
    )


def simulate_background_matches(
    session,
    user_school_id,
    *,
    background: bool = False,
    feature_games: int = FEATURE_FOCUS_GAMES,
    verbose: bool = False,
    log: Optional[Callable[[str], None]] = None,
    io: IOInterface | None = None,
    event_listeners: Optional[Sequence] = None,
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
        io=io,
        event_listeners=event_listeners,
    )
    return None