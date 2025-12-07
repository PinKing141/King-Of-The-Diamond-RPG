"""Lineup construction helpers keyed off school philosophy.

The match engine previously grabbed the first nine starters. This module
builds a batting order that mirrors Japanese high school archetypes
(Seido balanced chain, Yakushi bomb squad, Inashiro king court, etc.)
by mapping a school's philosophy to a lineup style and slotting players
accordingly.
"""
from __future__ import annotations

from typing import Callable, List, Tuple

from database.setup_db import Player
from world.school_philosophy import PHILOSOPHY_MATRIX

# Internal labels for lineup templates
_BALANCED = "balanced"
_AGGRESSIVE = "aggressive"
_ELITE = "elite"
_SMALL_BALL = "small_ball"
_CHAOS = "chaos"

_NAME_STYLE = {
    # Power / chaos schools
    "slugger army": _AGGRESSIVE,
    "machine gunners": _BALANCED,
    "glass cannons": _AGGRESSIVE,
    "clean-up crew": _AGGRESSIVE,
    "gamblers": _CHAOS,
    "dark horse": _CHAOS,
    "local bully": _AGGRESSIVE,
    # Balance / technical anchors
    "supreme dynasty": _ELITE,
    "national brand": _BALANCED,
    "pitching kingdom": _ELITE,
    "elite battery": _ELITE,
    "precision machines": _BALANCED,
    "scientific": _BALANCED,
    "modern freedom": _BALANCED,
    "average joes": _BALANCED,
    # Speed / pressure
    "small ball cult": _SMALL_BALL,
    "speed demons": _SMALL_BALL,
    # Defense-minded
    "defensive wall": _SMALL_BALL,
    "iron infield": _SMALL_BALL,
    "no-fly zone": _SMALL_BALL,
    "catcher general": _ELITE,
    # Guts / stamina
    "militaristic": _SMALL_BALL,
    "guts & glory": _CHAOS,
    "marathon men": _SMALL_BALL,
    "zen baseball": _BALANCED,
    # Ace-centric
    "one-man army": _ELITE,
    "twin aces": _ELITE,
    "fallen giant": _BALANCED,
    "public school hero": _SMALL_BALL,
    "academic elite": _BALANCED,
    "rich private school": _BALANCED,
    "delinquent squad": _AGGRESSIVE,
}


def _overall_score(p: Player) -> float:
    return float(getattr(p, "contact", 0) + getattr(p, "power", 0) + getattr(p, "speed", 0) + getattr(p, "fielding", 0))


def _offense_score(p: Player) -> float:
    return float(getattr(p, "contact", 0) + getattr(p, "power", 0) + getattr(p, "speed", 0) * 0.6)


def _defense_score(p: Player) -> float:
    return float(getattr(p, "fielding", 0) + getattr(p, "throwing", 0) * 0.4)


def _pitch_score(p: Player) -> float:
    return float(getattr(p, "velocity", 0) + getattr(p, "control", 0) + getattr(p, "movement", 0) + getattr(p, "stamina", 0) * 0.5)


def _lookup_focus(philosophy: str | None) -> str:
    if not philosophy:
        return "Balanced"
    data = PHILOSOPHY_MATRIX.get(philosophy)
    if data:
        return data.get("focus", "Balanced")
    # Fallback: treat raw label as focus if unknown
    return philosophy


def _resolve_style(philosophy: str | None) -> str:
    label = (philosophy or "").lower()
    if label in _NAME_STYLE:
        return _NAME_STYLE[label]
    focus = (_lookup_focus(philosophy) or "").lower()
    if focus in {"power", "core"} or "aggressive" in label:
        return _AGGRESSIVE
    if focus in {"speed"}:
        return _SMALL_BALL
    if focus in {"defense", "technical"}:
        return _BALANCED
    if focus in {"stamina", "guts"}:
        return _SMALL_BALL
    if focus in {"ace", "pitching", "battery"} or "elite" in label:
        return _ELITE
    if focus in {"random", "guts"} or label in {"gamblers", "dark horse"}:
        return _CHAOS
    return _BALANCED


# --- Position-aware starter selection ---
_POSITION_GROUPS: dict[str, Tuple[str, ...]] = {
    "P": ("p", "pitcher"),
    "C": ("c", "catcher"),
    "1B": ("1b", "first base", "first"),
    "2B": ("2b", "second base", "second"),
    "3B": ("3b", "third base", "third"),
    "SS": ("ss", "shortstop", "short"),
    "LF": ("lf", "left field", "left"),
    "CF": ("cf", "center field", "center"),
    "RF": ("rf", "right field", "right"),
}


def _normalize_pos(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _position_bucket(player: Player) -> str | None:
    pos = _normalize_pos(getattr(player, "position", None))
    for label, tokens in _POSITION_GROUPS.items():
        if pos in tokens:
            return label
    return None


def _composite_score(p: Player, weight_off=0.6, weight_def=0.4) -> float:
    starter_bonus = 8.0 if getattr(p, "is_starter", False) else 0.0
    return _offense_score(p) * weight_off + _defense_score(p) * weight_def + starter_bonus


def select_starting_nine(roster: List[Player], philosophy: str | None = None) -> List[Player]:
    """Choose a defensible starting nine covering all positions.

    - Ensures each defensive spot (P, C, 1B, 2B, 3B, SS, LF, CF, RF) is filled if possible.
    - Uses composite (batting 60% / defense 40%) with a small starter flag bonus.
    - Falls back to best remaining players if a position pool is empty.
    """

    players = [p for p in roster if p is not None]
    if not players:
        return []

    pool = players.copy()
    lineup: list[Player | None] = [None] * 9
    targets = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]

    # 1) Fill by position need
    for idx, label in enumerate(targets):
        candidates = [p for p in pool if _position_bucket(p) == label]
        if label == "P":
            pick = _pick_best(candidates, _pitch_score)
        elif label == "C":
            pick = _pick_best(candidates, lambda p: _defense_score(p) * 1.2 + getattr(p, "contact", 0) * 0.5)
        else:
            pick = _pick_best(candidates, _composite_score)
        if pick:
            lineup[idx] = pick
            pool.remove(pick)

    # 2) Fill any gaps with best remaining overall
    for idx, slot in enumerate(lineup):
        if slot is None and pool:
            best = _pick_best(pool, _composite_score)
            if best:
                lineup[idx] = best

    # 3) If still short (roster < 9), trim empties
    starters = [p for p in lineup if p is not None]

    # Philosophy can influence weights lightly (power lineups value offense a bit more)
    style = _resolve_style(philosophy)
    if style == _AGGRESSIVE:
        starters = sorted(starters, key=lambda p: _composite_score(p, weight_off=0.7, weight_def=0.3), reverse=True)[:9]
    elif style == _SMALL_BALL:
        starters = sorted(starters, key=lambda p: _composite_score(p, weight_off=0.5, weight_def=0.5), reverse=True)[:9]
    else:
        starters = starters[:9]

    return starters


def _pick_best(pool: list[Player], key_fn: Callable[[Player], float]) -> Player | None:
    if not pool:
        return None
    best = max(pool, key=key_fn)
    pool.remove(best)
    return best


def _fill_remaining(lineup: list[Player | None], pool: list[Player], key_fn: Callable[[Player], float]) -> None:
    for idx, slot in enumerate(lineup):
        if slot is None and pool:
            lineup[idx] = _pick_best(pool, key_fn)


def _has_two_way_ace(pool: list[Player]) -> Player | None:
    for p in pool:
        if getattr(p, "position", "").lower().startswith("p") and (getattr(p, "contact", 0) + getattr(p, "power", 0)) >= 130:
            return p
    return None


def optimize_lineup(roster: List[Player], philosophy: str | None = None) -> List[Player]:
    """Return an ordered list of up to 9 players based on philosophy-driven templates.

    This keeps the code lightweight but produces distinct identities per school.
    """
    players = [p for p in roster if p is not None]
    if not players:
        return []

    starters = sorted(players, key=_overall_score, reverse=True)[:9]
    if len(starters) <= 1:
        return starters

    style = _resolve_style(philosophy)
    pool = starters.copy()
    lineup: list[Player | None] = [None] * min(len(starters), 9)

    if style == _BALANCED:
        lineup[3] = _pick_best(pool, lambda p: getattr(p, "power", 0) * 1.5 + getattr(p, "contact", 0))
        lineup[0] = _pick_best(pool, lambda p: getattr(p, "speed", 0) * 2 + getattr(p, "contact", 0))
        lineup[1] = _pick_best(pool, lambda p: getattr(p, "contact", 0) * 2 + getattr(p, "fielding", 0))
        lineup[2] = _pick_best(pool, lambda p: getattr(p, "contact", 0) + getattr(p, "power", 0))
        lineup[4] = _pick_best(pool, lambda p: getattr(p, "power", 0))
        _fill_remaining(lineup, pool, lambda p: getattr(p, "contact", 0) + getattr(p, "power", 0) * 0.4)

    elif style == _AGGRESSIVE:
        lineup[3] = _pick_best(pool, lambda p: getattr(p, "power", 0))
        lineup[0] = _pick_best(pool, lambda p: getattr(p, "power", 0) + getattr(p, "speed", 0))
        lineup[2] = _pick_best(pool, lambda p: getattr(p, "power", 0))
        lineup[4] = _pick_best(pool, lambda p: getattr(p, "power", 0))
        lineup[1] = _pick_best(pool, lambda p: getattr(p, "contact", 0))
        _fill_remaining(lineup, pool, lambda p: getattr(p, "power", 0) + getattr(p, "contact", 0) * 0.3)

    elif style == _ELITE:
        ace = _has_two_way_ace(pool)
        if ace:
            pool.remove(ace)
            lineup[4] = ace
        lineup[3] = _pick_best(pool, lambda p: getattr(p, "power", 0) + getattr(p, "contact", 0) * 1.2)
        lineup[0] = _pick_best(pool, lambda p: getattr(p, "contact", 0) + getattr(p, "speed", 0))
        lineup[2] = _pick_best(pool, lambda p: getattr(p, "contact", 0))
        lineup[1] = _pick_best(pool, lambda p: getattr(p, "fielding", 0) + getattr(p, "contact", 0))
        if lineup[4] is None:
            lineup[4] = _pick_best(pool, lambda p: getattr(p, "power", 0) + getattr(p, "contact", 0))
        _fill_remaining(lineup, pool, _overall_score)

    elif style == _SMALL_BALL:
        lineup[0] = _pick_best(pool, lambda p: getattr(p, "speed", 0) * 2 + getattr(p, "contact", 0))
        lineup[1] = _pick_best(pool, lambda p: getattr(p, "contact", 0) + getattr(p, "fielding", 0) + getattr(p, "speed", 0))
        lineup[2] = _pick_best(pool, lambda p: getattr(p, "contact", 0) + getattr(p, "speed", 0) * 0.5)
        lineup[3] = _pick_best(pool, lambda p: getattr(p, "power", 0) + getattr(p, "contact", 0) * 0.8)
        lineup[4] = _pick_best(pool, lambda p: getattr(p, "contact", 0) + getattr(p, "fielding", 0) + getattr(p, "speed", 0) * 0.25)
        _fill_remaining(lineup, pool, lambda p: getattr(p, "fielding", 0) + getattr(p, "speed", 0) * 0.6 + getattr(p, "contact", 0) * 0.4)

    else:  # _CHAOS fallback
        lineup[3] = _pick_best(pool, lambda p: getattr(p, "power", 0))
        lineup[0] = _pick_best(pool, lambda p: getattr(p, "contact", 0) + getattr(p, "power", 0))
        lineup[1] = _pick_best(pool, lambda p: getattr(p, "speed", 0) + getattr(p, "contact", 0))
        lineup[2] = _pick_best(pool, lambda p: getattr(p, "power", 0))
        _fill_remaining(lineup, pool, lambda p: getattr(p, "contact", 0) + getattr(p, "power", 0) + getattr(p, "speed", 0) * 0.2)

    return [p for p in lineup if p is not None]
