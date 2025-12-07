from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database.setup_db import CoachStrategyMod
from game.personnel.coach_personalities import get_personality_profile


def _serialize_payload(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    if payload is None:
        return None
    return json.dumps(payload)


def _parse_payload(mod: CoachStrategyMod) -> Optional[Dict[str, Any]]:
    if not mod.payload:
        return None
    try:
        return json.loads(mod.payload)
    except json.JSONDecodeError:
        return None


def set_strategy_modifier(
    session: Session,
    school_id: int,
    effect_type: str,
    games: int = 1,
    target_player_id: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> CoachStrategyMod:
    mod = CoachStrategyMod(
        school_id=school_id,
        effect_type=effect_type,
        games_remaining=max(1, games),
        target_player_id=target_player_id,
        payload=_serialize_payload(payload),
    )
    session.add(mod)
    session.commit()
    return mod


def get_active_modifiers(session: Session, school_id: int) -> List[CoachStrategyMod]:
    return session.query(CoachStrategyMod).filter_by(school_id=school_id).all()


def get_active_modifiers_by_type(
    session: Session, school_id: int, effect_type: str
) -> List[CoachStrategyMod]:
    return (
        session.query(CoachStrategyMod)
        .filter_by(school_id=school_id, effect_type=effect_type)
        .all()
    )


def has_modifier(
    session: Session,
    school_id: int,
    effect_type: str,
    target_player_id: Optional[int] = None,
) -> bool:
    query = session.query(CoachStrategyMod).filter_by(
        school_id=school_id,
        effect_type=effect_type,
    )
    if target_player_id is not None:
        query = query.filter(CoachStrategyMod.target_player_id == target_player_id)
    return query.first() is not None


def get_coach_strategy_modifiers(coach) -> Dict[str, float]:
    """Return gameplay levers influenced by coach personality bias."""
    if not coach:
        return {}

    profile = get_personality_profile(getattr(coach, "personality", "Stoic"))
    bias = profile.get("bias")
    mods = {
        "bunt_tendency": 1.0,
        "steal_tendency": 1.0,
        "pitch_change_tolerance": 1.0,
        "pinch_hit_aggression": 1.0,
    }

    if bias == "power":
        mods["bunt_tendency"] = 0.4
        mods["pinch_hit_aggression"] = 1.3
    elif bias == "bunt":
        mods["bunt_tendency"] = 1.8
        mods["steal_tendency"] = 0.8
    elif bias == "gambler":
        mods["steal_tendency"] = 1.5
        mods["pinch_hit_aggression"] = 1.5
        mods["bunt_tendency"] = 0.2
    elif bias == "defense":
        mods["pitch_change_tolerance"] = 0.7

    return mods


def ensure_personality_strategy_mods(session: Session, coach, school_id: int) -> None:
    """Set lightweight match directives that mirror personality bias."""
    if not coach:
        return

    profile = get_personality_profile(getattr(coach, "personality", "Stoic"))
    bias = profile.get("bias")

    def _queue(effect: str) -> None:
        if has_modifier(session, school_id, effect_type=effect):
            return
        set_strategy_modifier(session, school_id, effect, games=5)

    if bias in {"bunt", "defense", "tactical", "standard"}:
        _queue("small_ball")
    elif bias in {"power", "aggro", "gambler", "speed"}:
        _queue("power_focus")


def get_resting_player_ids(session: Session, school_id: int) -> List[int]:
    mods = get_active_modifiers_by_type(session, school_id, 'rest_player')
    return [m.target_player_id for m in mods if m.target_player_id]


def consume_strategy_mods(session: Session, school_id: int) -> None:
    mods = get_active_modifiers(session, school_id)
    if not mods:
        return
    for mod in mods:
        mod.games_remaining -= 1
        if mod.games_remaining <= 0:
            session.delete(mod)
        else:
            session.add(mod)
    session.commit()


def export_mod_descriptors(session: Session, school_id: int) -> List[Dict[str, Any]]:
    descriptors: List[Dict[str, Any]] = []
    for mod in get_active_modifiers(session, school_id):
        descriptors.append(
            {
                'type': mod.effect_type,
                'target_player_id': mod.target_player_id,
                'payload': _parse_payload(mod),
            }
        )
    return descriptors
