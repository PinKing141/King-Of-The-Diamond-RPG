from __future__ import annotations

import random
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

from database.setup_db import Player, PlayerRelationship
from game.archetypes import get_player_archetype

REL_MIN = 0
REL_MAX = 100


def _clamp(value: float, low: int = REL_MIN, high: int = REL_MAX) -> int:
    return int(max(low, min(high, round(value))))


def get_or_create_relationship(session: Session, player_id: int) -> PlayerRelationship:
    rel = session.query(PlayerRelationship).filter_by(player_id=player_id).one_or_none()
    if rel:
        return rel

    rel = PlayerRelationship(player_id=player_id)
    session.add(rel)
    session.flush()
    return rel


def _choose_best_player(candidates, default=None, *, key=None):
    if not candidates:
        return default
    if key is None:
        return random.choice(candidates)
    return max(candidates, key=key)


def _candidate_players(session: Session, school_id: int, exclude_id: int):
    return session.query(Player).filter(Player.school_id == school_id, Player.id != exclude_id).all()


CONFLICT_PROFILES = {
    "minor": {
        "captain": -2,
        "battery": -2,
        "battery_partner_bonus": -1,
        "rivalry": 1,
    },
    "major": {
        "captain": -5,
        "battery": -4,
        "battery_partner_bonus": -2,
        "rivalry": 3,
    },
}


REBOUND_THRESHOLDS: Sequence[tuple[int, int, int]] = (
    (80, 4, -4),
    (72, 3, -3),
    (65, 2, -2),
)

CONFIDENCE_GAIN_TIERS: Sequence[tuple[int, int, int, int]] = (
    (12, 4, 3, -3),
    (8, 2, 1, -1),
)

CONFIDENCE_DROP_TIERS: Sequence[tuple[int, int, int, int]] = (
    (-12, -5, -3, 4),
    (-8, -2, -1, 2),
)

CONFIDENCE_REASON_NUDGES = {
    "slump_break": (2, 1, -2),
    "heroics": (1, 1, -1),
    "discipline": (1, 0, 0),
    "error": (-1, -2, 2),
    "wild_pitch": (-2, -1, 2),
    "strikeout": (0, 0, 1),
}

ARCHETYPE_CONFLICT_SCALE = {
    "firebrand": 1.35,
    "showman": 1.2,
    "sparkplug": 1.15,
    "guardian": 0.7,
    "steady": 0.85,
    "strategist": 0.9,
}

ARCHETYPE_REBOUND_BONUS = {
    "guardian": (2, 2),
    "steady": (1, 1),
    "sparkplug": (0, 1),
}


def seed_relationships(session: Session, player: Player) -> PlayerRelationship:
    rel = get_or_create_relationship(session, player.id)
    school_players = _candidate_players(session, player.school_id, player.id)

    if not rel.captain_id and school_players:
        captain = next((p for p in school_players if p.is_captain), None)
        if not captain:
            captain = _choose_best_player(
                school_players,
                key=lambda p: (p.year or 1, p.trust_baseline or 50, p.overall or 0),
            )
        if captain:
            rel.captain_id = captain.id
            rel.captain_rel = random.randint(55, 70)

    if not rel.battery_partner_id and school_players:
        if player.position == "Pitcher":
            pool = [p for p in school_players if p.position == "Catcher"]
        elif player.position == "Catcher":
            pool = [p for p in school_players if p.position == "Pitcher"]
        else:
            pool = [p for p in school_players if p.position == "Pitcher"]
        partner = _choose_best_player(pool, key=lambda p: (p.trust_baseline or 50, p.overall or 0))
        if partner:
            rel.battery_partner_id = partner.id
            rel.battery_rel = random.randint(50, 65)

    if not rel.rival_id and school_players:
        pool = [p for p in school_players if p.position == player.position]
        if not pool:
            pool = school_players
        rival = _choose_best_player(pool, key=lambda p: (p.year or 1, p.overall or 0))
        if rival:
            rel.rival_id = rival.id
            rel.rivalry_score = random.randint(40, 55)

    session.add(rel)
    session.commit()
    return rel


def adjust_relationship(session: Session, rel: PlayerRelationship, field: str, delta: float) -> PlayerRelationship:
    if not hasattr(rel, field):
        return rel
    current = getattr(rel, field) or 0
    setattr(rel, field, _clamp(current + delta))
    session.add(rel)
    session.flush()
    return rel


def get_rival_pressure_modifier(rel: Optional[PlayerRelationship]) -> float:
    if not rel:
        return 0.0
    base = (rel.rivalry_score or 45) - 45
    return base / 50.0  # +/- up to roughly 1.1x pressure bonus


def apply_conflict_penalty(
    session: Session,
    players: Iterable[Player],
    *,
    severity: str = "minor",
) -> None:
    """Dull captain/battery trust after blowups so locker-room tension lingers."""

    profile = CONFLICT_PROFILES.get(severity, CONFLICT_PROFILES["minor"])
    participants = [p for p in players if p is not None]
    participant_ids = {getattr(p, "id", None) for p in participants}
    participant_ids.discard(None)
    if not participants or not participant_ids:
        return

    for player in participants:
        scale = ARCHETYPE_CONFLICT_SCALE.get(_player_archetype(player), 1.0)
        rel = seed_relationships(session, player)
        if rel.captain_id:
            adjust_relationship(session, rel, "captain_rel", round(profile["captain"] * scale))
        if rel.battery_partner_id:
            delta = profile["battery"]
            if rel.battery_partner_id in participant_ids:
                delta += profile["battery_partner_bonus"]
            adjust_relationship(session, rel, "battery_rel", round(delta * scale))
        if rel.rival_id and rel.rival_id in participant_ids:
            adjust_relationship(session, rel, "rivalry_score", round(profile["rivalry"] * scale))


def register_morale_rebound(
    session: Session,
    player: Player,
    *,
    reason: Optional[str] = None,
) -> Optional[PlayerRelationship]:
    """Nudge trust upward when a player steadies themselves after a slump."""

    if player is None:
        return None
    morale = getattr(player, "morale", 60) or 60
    rel = seed_relationships(session, player)

    applied = False
    for cutoff, trust_gain, rivalry_shift in REBOUND_THRESHOLDS:
        if morale >= cutoff:
            adjust_relationship(session, rel, "captain_rel", trust_gain)
            adjust_relationship(session, rel, "battery_rel", max(1, trust_gain - 1))
            if reason == "slump_cleared" and rivalry_shift:
                adjust_relationship(session, rel, "rivalry_score", rivalry_shift)
            applied = True
            break

    if not applied and reason == "slump_cleared":
        # Even slight recovery earns a token captain trust boost.
        adjust_relationship(session, rel, "captain_rel", 1)

    arch = _player_archetype(player)
    bonus = ARCHETYPE_REBOUND_BONUS.get(arch)
    if bonus:
        cap_delta, bat_delta = bonus
        adjust_relationship(session, rel, "captain_rel", cap_delta)
        adjust_relationship(session, rel, "battery_rel", bat_delta)

    return rel


def _top_confidence_event(info: Mapping[str, Any], positive: bool = True) -> Optional[Mapping[str, Any]]:
    events = info.get("events") if info else None
    if not events:
        return None
    filtered = [evt for evt in events if (evt.get("delta", 0) > 0) == positive]
    if not filtered:
        return None
    key = max if positive else min
    return key(filtered, key=lambda evt: evt.get("delta", 0))


def _apply_relationship_shift(session: Session, rel: PlayerRelationship, captain: int = 0, battery: int = 0, rivalry: int = 0) -> None:
    if captain and rel.captain_id:
        adjust_relationship(session, rel, "captain_rel", captain)
    if battery and rel.battery_partner_id:
        adjust_relationship(session, rel, "battery_rel", battery)
    if rivalry and rel.rival_id:
        adjust_relationship(session, rel, "rivalry_score", rivalry)


def _apply_confidence_tiers(session: Session, rel: PlayerRelationship, max_gain: float, max_drop: float) -> None:
    for cutoff, cap_delta, bat_delta, rival_delta in CONFIDENCE_GAIN_TIERS:
        if max_gain >= cutoff:
            _apply_relationship_shift(session, rel, cap_delta, bat_delta, rival_delta)
            break
    for cutoff, cap_delta, bat_delta, rival_delta in CONFIDENCE_DROP_TIERS:
        if max_drop <= cutoff:
            _apply_relationship_shift(session, rel, cap_delta, bat_delta, rival_delta)
            break


def _apply_reason_bias(session: Session, rel: PlayerRelationship, event: Optional[Mapping[str, Any]]) -> None:
    if not event:
        return
    reason = event.get("reason")
    if not reason:
        return
    deltas = CONFIDENCE_REASON_NUDGES.get(reason)
    if not deltas:
        return
    cap_delta, bat_delta, rival_delta = deltas
    _apply_relationship_shift(session, rel, cap_delta, bat_delta, rival_delta)


def apply_confidence_relationships(session: Session, summary: Optional[Mapping[int, Mapping[str, Any]]]) -> None:
    """Translate confidence swings into relationship nudges so storylines feel connected."""

    if not summary:
        return
    for player_id, info in summary.items():
        player = session.get(Player, player_id)
        if not player:
            continue
        rel = seed_relationships(session, player)
        max_gain = info.get("max_gain", 0)
        max_drop = info.get("max_drop", 0)
        _apply_confidence_tiers(session, rel, max_gain, max_drop)
        _apply_reason_bias(session, rel, _top_confidence_event(info, positive=True))
        _apply_reason_bias(session, rel, _top_confidence_event(info, positive=False))
    session.commit()


def _player_archetype(player: Optional[Player]) -> str:
    if not player:
        return "steady"
    return get_player_archetype(player)
