"""Lightweight helpers for pitch mastery progression.

Phase 1: XP-only levels with static thresholds. Higher phases can swap in
curves or per-pitch tuning while keeping this API stable.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError

from database.setup_db import PitchRepertoire
from core.io_interface import IOInterface
from ui.ui_core import BAR_WIDTH as UI_BAR_WIDTH, colored_bar as ui_colored_bar, simple_bar as ui_simple_bar

logger = logging.getLogger(__name__)

# XP required to reach each level (levels now start at 0 for unlearned pitches).
# Tuning: bump caps to slow early climbs and make higher tiers feel earned.
MASTERY_THRESHOLDS = [90, 220, 450, 800, 1200, 1700, 2300, 3000]


def mastery_level_for_xp(xp: int) -> int:
    """Return mastery level for the given XP.

    XP is clamped to 0. Levels scale gently so Phase 1 progression is visible
    without requiring full game-season grind.
    """
    safe_xp = max(0, int(xp or 0))
    level = 0
    for idx, threshold in enumerate(MASTERY_THRESHOLDS, start=1):
        if safe_xp >= threshold:
            level = idx
        else:
            break
    return level


def mastery_progress(xp: int) -> Tuple[int, Optional[int]]:
    """Return (level, next_threshold) for UI display."""
    level = mastery_level_for_xp(xp)
    next_threshold = MASTERY_THRESHOLDS[level] if level < len(MASTERY_THRESHOLDS) else None
    return level, next_threshold


def _log(message: str, *, io: Optional[IOInterface] = None, level: str = "info") -> None:
    if io:
        io.log(message, level=level)
    else:
        print(message)


def _prompt(prompt: str, *, io: Optional[IOInterface] = None, options: Optional[list[str]] = None) -> str:
    if io:
        return io.prompt(prompt, options=options)
    while True:
        try:
            response = input(prompt)
        except (EOFError, KeyboardInterrupt):
            return ""
        if options is None or response in options:
            return response


# --- Phase 2 helpers: in-game accrual ---

# Base XP tuning: tiny reward per pitch, bigger for whiffs/weak contact; capped so
# single pitches do not over-accelerate mastery.
_OUTCOME_XP = {
    "Strike:Looking": 2,
    "Strike:Swinging": 3,
    "Foul": 1,
    "InPlay:weak": 2,
    "InPlay:hard": 0,
    "Ball": 0,
}
_BASE_XP_PER_PITCH = 1
_MAX_XP_PER_PITCH = 6


_SIGNATURE_LIBRARY = {
    "fastball": "Late Life",
    "heater": "Late Life",
    "sinker": "Heavy",
    "splitter": "Disappear",
    "split": "Disappear",
    "changeup": "Fade",
    "change": "Fade",
    "breaker": "Wipeout",
    "curve": "Wipeout",
    "slider": "Wipeout",
    "sweeper": "Wipeout",
}


def _pick_signature_tag(pitch_name: str) -> str:
    try:
        from match_engine.pitch_definitions import PITCH_TYPES
    except ImportError:
        PITCH_TYPES = {}
    key = pitch_name or ""
    family = (PITCH_TYPES.get(key) or {}).get("family", "").lower()
    lowered = key.lower()
    for needle, tag in _SIGNATURE_LIBRARY.items():
        if needle in lowered or needle == family:
            return tag
    return "Resolve"


def _buffer(state) -> Dict[tuple[int, str], int]:
    buf = getattr(state, "pitch_mastery_buffer", None)
    if buf is None:
        buf = {}
        state.pitch_mastery_buffer = buf
    return buf


def record_pitch_xp(
    state,
    pitcher_id: Optional[int],
    pitch_name: Optional[str],
    result,
    *,
    family: Optional[str] = None,
) -> int:
    """Accumulate mastery XP in-state; flush to DB later.

    Rewards:
    - +1 base per pitch
    - +2/+3 for strikes (called vs swinging)
    - +1 for fouls (chase fouls treated as swing)
    - +2 for weak contact in play, 0 for hard contact
    XP is clamped per pitch to avoid runaway gains.
    """
    if not state or not pitcher_id or not pitch_name or result is None:
        return 0

    outcome = getattr(result, "outcome", "") or ""
    desc = getattr(result, "description", "") or ""
    contact_quality = getattr(result, "contact_quality", None)

    trail_penalty = 0
    mix_bonus = 0
    if family and hasattr(state, "pitch_mix_tracker"):
        entry = getattr(state, "pitch_mix_tracker", {}).get(pitcher_id)
        if entry and family and entry.get("last"):
            tail = entry["last"][-3:]
            if tail and all(fam == family for fam in tail):
                trail_penalty = 1
        if entry and len((entry.get("families") or {})) >= 3:
            mix_bonus = 1

    xp = _BASE_XP_PER_PITCH
    if outcome == "Strike":
        xp += _OUTCOME_XP.get("Strike:Swinging" if desc == "Swinging Miss" else "Strike:Looking", 0)
    elif outcome == "Foul":
        xp += _OUTCOME_XP["Foul"]
    elif outcome == "InPlay":
        if contact_quality is not None and contact_quality < 20:
            xp += _OUTCOME_XP["InPlay:weak"]
        elif contact_quality is not None and contact_quality >= 35:
            xp += _OUTCOME_XP["InPlay:hard"]
        else:
            xp += 1
    else:  # Ball or anything unusual
        xp += _OUTCOME_XP.get(outcome, 0)

    xp = max(0, min(_MAX_XP_PER_PITCH, xp - trail_penalty + mix_bonus))

    buf = _buffer(state)
    key = (int(pitcher_id), str(pitch_name))
    buf[key] = buf.get(key, 0) + xp

    report = getattr(state, "pitch_mastery_report", None)
    if report is None:
        report = {}
        state.pitch_mastery_report = report
    slot = report.setdefault(str(pitch_name), {"xp": 0, "predictable": 0, "mix_bonus": 0})
    slot["xp"] += xp
    if trail_penalty:
        slot["predictable"] += 1
        logs = getattr(state, "logs", None)
        if isinstance(logs, list) and len(logs) < 500:
            logs.append(f"[Pitch Lab] Hitters are timing the {pitch_name}; mix it up for better gains.")
    if mix_bonus:
        slot["mix_bonus"] += 1
    return xp


def flush_pitch_xp(state) -> int:
    """Persist buffered mastery XP into the DB session if present."""
    if not state:
        return 0
    buf = getattr(state, "pitch_mastery_buffer", None) or {}
    if not buf:
        return 0
    session = getattr(state, "db_session", None)
    if session is None:
        return 0

    from database.setup_db import PitchRepertoire, Player  # Local import to avoid cycles

    applied = 0
    unlock_messages = []
    for (pitcher_id, pitch_name), delta in buf.items():
        rows = session.query(PitchRepertoire).filter_by(player_id=pitcher_id, pitch_name=pitch_name).all()
        for row in rows:
            prior_level = getattr(row, "mastery_level", 0) or 0
            row.mastery_xp = max(0, int(getattr(row, "mastery_xp", 0) or 0) + delta)
            row.mastery_level = mastery_level_for_xp(row.mastery_xp)

            # Signature awakenings at Lv3+: assign a tag, mark ready, auto-unlock if points available.
            if row.mastery_level >= 3 and not getattr(row, "signature_tag", None):
                row.signature_tag = _pick_signature_tag(row.pitch_name)
                row.signature_ready = True
                player = session.get(Player, row.player_id)
                if player:
                    if player.ability_points and player.ability_points > 0 and row.mastery_level >= 1:
                        player.ability_points -= 1
                        row.signature_unlocked = True
                        unlock_messages.append(
                            f"{player.name} refined their {row.pitch_name}: {row.signature_tag} unlocked (1 AP)."
                        )
                    else:
                        unlock_messages.append(
                            f"{player.name} is ready to unlock {row.pitch_name} ({row.signature_tag}); visit Pitch Lab."
                        )

            session.add(row)
            applied += delta
    session.commit()
    state.pitch_mastery_buffer = {}

    logs = getattr(state, "logs", None)
    if isinstance(logs, list) and unlock_messages:
        logs.extend(unlock_messages)
    return applied


# --- Phase 4 helpers: decay, lab, reporting ---


def apply_mastery_decay(session, player, *, maintained: bool = False, log: Optional[list] = None) -> int:
    """Weekly decay/maintenance applied to a player's pitches.

    -2 XP per pitch baseline; -4 if not maintained; capped at not going below 0.
    """
    if session is None or player is None:
        return 0
    repertoire = getattr(player, "pitch_repertoire", None)
    if repertoire is None:
        try:
            repertoire = session.query(PitchRepertoire).filter_by(player_id=player.id).all()
        except SQLAlchemyError as exc:
            logger.warning("Pitch mastery decay skipped for %s: %s", getattr(player, "id", None), exc)
            repertoire = []
    if not repertoire:
        return 0
    decay_total = 0
    step = 2 if maintained else 4
    for pitch in repertoire:
        if getattr(pitch, "mastery_xp", 0) <= 0:
            continue
        before = pitch.mastery_xp
        pitch.mastery_xp = max(0, pitch.mastery_xp - step)
        pitch.mastery_level = mastery_level_for_xp(pitch.mastery_xp)
        session.add(pitch)
        decay_total += before - pitch.mastery_xp
    session.commit()
    if log is not None and decay_total:
        log.append(f"Pitch feel faded slightly (-{decay_total} XP). Bullpen work prevents heavier decay.")
    return decay_total


def _level_window(level: int) -> Tuple[int, Optional[int]]:
    prev = MASTERY_THRESHOLDS[level - 1] if level > 0 else 0
    nxt = MASTERY_THRESHOLDS[level] if level < len(MASTERY_THRESHOLDS) else None
    return prev, nxt


def open_pitch_lab(session, player, *, io: Optional[IOInterface] = None) -> None:
    if session is None or player is None:
        _log("No player loaded.", io=io)
        return
    try:
        session.refresh(player)
    except SQLAlchemyError as exc:
        logger.debug("Pitch lab refresh failed for %s: %s", getattr(player, "id", None), exc)
    repertoire = session.query(PitchRepertoire).filter_by(player_id=player.id).all()
    if not repertoire:
        _log("No recorded pitches yet.", io=io)
        _prompt("Press Enter to exit.", io=io)
        return
    while True:
        _log("\n=== Pitch Lab ===", io=io)
        _log(f"Ability Points: {getattr(player, 'ability_points', 0) or 0}", io=io)
        for idx, pitch in enumerate(repertoire, start=1):
            xp = int(getattr(pitch, "mastery_xp", 0) or 0)
            level = mastery_level_for_xp(xp)
            sig = getattr(pitch, "signature_tag", None)
            unlocked = bool(getattr(pitch, "signature_unlocked", False))
            ready = bool(getattr(pitch, "signature_ready", False))
            prev, nxt = _level_window(level)
            span = None if nxt is None else max(1, nxt - prev)
            progress = max(0, xp - prev)
            bar_value = progress if span is not None else UI_BAR_WIDTH
            bar = ui_colored_bar(min(bar_value, span or UI_BAR_WIDTH), max_value=span or UI_BAR_WIDTH)
            progress_txt = "Mastered" if nxt is None else f"{progress}/{span}"
            label = f"{idx}. {pitch.pitch_name} Lv{level} {bar} {progress_txt}"
            if sig:
                label += f" | Sig: {sig}{' (Unlocked)' if unlocked else ' (Ready)' if ready else ''}"
            _log(label, io=io)
        _log("[U] Unlock first ready signature (1 AP)  |  [Q] Back", io=io)
        choice = _prompt("> ", io=io).strip().lower()
        if choice == "q":
            break
        if choice == "u":
            ready_pitch = next((p for p in repertoire if getattr(p, "signature_ready", False) and not getattr(p, "signature_unlocked", False)), None)
            if not ready_pitch:
                _log("No signature-ready pitches.", io=io)
                continue
            if (player.ability_points or 0) <= 0:
                _log("Need 1 Ability Point to unlock.", io=io)
                continue
            if mastery_level_for_xp(getattr(ready_pitch, "mastery_xp", 0)) < 1:
                _log("Need at least Lv1 mastery before spending Ability Points here.", io=io)
                continue
            player.ability_points -= 1
            ready_pitch.signature_unlocked = True
            session.add(player)
            session.add(ready_pitch)
            session.commit()
            _log(f"Unlocked {ready_pitch.pitch_name} signature: {ready_pitch.signature_tag}.", io=io)
            continue
        try:
            idx = int(choice)
        except ValueError:
            continue
        if idx < 1 or idx > len(repertoire):
            continue
        pitch = repertoire[idx - 1]
        xp = int(getattr(pitch, 'mastery_xp', 0) or 0)
        level = mastery_level_for_xp(xp)
        prev, nxt = _level_window(level)
        span = None if nxt is None else max(1, nxt - prev)
        progress = max(0, xp - prev)
        bar_value = progress if span is not None else UI_BAR_WIDTH
        bar = ui_simple_bar(min(bar_value, span or UI_BAR_WIDTH), max_value=span or UI_BAR_WIDTH, width=UI_BAR_WIDTH)
        progress_txt = "Mastered" if nxt is None else f"Progress: {progress}/{span}"
        _log(
            f"{pitch.pitch_name}: XP {xp} | Lv {level}\n"
            f"{progress_txt} {bar}\n"
            f"Signature: {getattr(pitch, 'signature_tag', 'None')} ({'Unlocked' if getattr(pitch, 'signature_unlocked', False) else 'Locked'})",
            io=io,
        )
        _prompt("Press Enter...", io=io)


def summarize_mastery_report(state) -> Optional[str]:
    report = getattr(state, "pitch_mastery_report", None)
    if not report:
        return None
    lines = []
    for name, payload in report.items():
        xp = payload.get("xp", 0)
        pred = payload.get("predictable", 0)
        lines.append(f"{name}: +{xp} XP{' (predictable)' if pred else ''}")
    return " | ".join(lines) if lines else None
