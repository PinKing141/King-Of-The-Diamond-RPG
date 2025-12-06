"""Core offseason helpers extracted from the season engine."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from database.populate_japan import (
    generate_pitch_arsenal,
    generate_stats,
    get_random_english_name,
)
from database.setup_db import Player, School
from game.rng import get_rng
from world.school_philosophy import get_philosophy
from game.personality import roll_player_personality
from game.player_generation import seed_negative_traits
from game.trait_logic import seed_initial_traits

rng = get_rng()
BASE_ATTRIBUTES = [
    "velocity",
    "control",
    "command",
    "movement",
    "speed",
    "contact",
    "power",
    "fielding",
    "throwing",
    "stamina",
]


def graduate_third_years(session: Session) -> int:
    """Remove all third-year players and return the number of graduates."""
    deleted = session.query(Player).filter(Player.year == 3).delete()
    session.flush()
    return deleted or 0


def apply_physical_growth(players: Iterable[Player]) -> None:
    """Apply height, weight, and attribute growth for the offseason."""
    for player in players:
        height_gain = _grow_height(player)
        _grow_weight(player, height_gain)
        _grow_attributes(player)
        if getattr(player, "position", "") == "Pitcher":
            _grow_pitcher_velocity(player)


def recruit_freshmen(session: Session, target_roster: int = 18) -> int:
    """Generate enough first-years per school to reach the target roster size."""
    schools = session.query(School).all()
    total_new_players = 0

    new_recruits: list[Player] = []
    for school in schools:
        current_roster = len(school.players)
        needed = max(5, target_roster - current_roster)

        phil_name, phil_data = get_philosophy(school.philosophy)
        focus = phil_data.get("focus", "Balanced")

        for _ in range(needed):
            position, specific = _roll_position()
            stats = generate_stats(position, specific, focus)
            _ensure_physical_stats(stats)
            _apply_focus_bias(stats, position, specific, focus)
            last_name, first_name = get_random_english_name('M')

            valid_cols = {c.key for c in Player.__table__.columns}
            filtered_stats = {k: v for k, v in stats.items() if k in valid_cols}
            traits = roll_player_personality(school)
            filtered_stats['drive'] = traits['drive']
            filtered_stats['loyalty'] = traits['loyalty']
            filtered_stats['volatility'] = traits['volatility']

            display_name = f"{last_name} {first_name}"

            player = Player(
                name=display_name,
                first_name=first_name,
                last_name=last_name,
                position=position,
                year=1,
                school_id=school.id,
                jersey_number=rng.randint(20, 99),
                role="BENCH",
                fatigue=0,
                injury_days=0,
                growth_tag=stats.get('growth_tag', 'Normal'),
                potential_grade=stats.get('potential_grade', 'C'),
                **filtered_stats,
            )

            if position == "Pitcher":
                class PseudoPlayer:
                    def __init__(self, stat_block):
                        self.control = stat_block.get('control', 50)
                        self.movement = stat_block.get('movement', 50)

                try:
                    player.pitch_repertoire = generate_pitch_arsenal(
                        PseudoPlayer(stats), focus, stats.get('arm_slot', 'Three-Quarters')
                    )
                except Exception:
                    pass

                session.add(player)
                new_recruits.append(player)
            total_new_players += 1

            session.flush()
            seed_initial_traits(session, new_recruits)
            seed_negative_traits(session, new_recruits)
            session.commit()
    return total_new_players


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _roll_position() -> tuple[str, str]:
    roll = rng.random()
    if roll < 0.4:
        return "Pitcher", "P"
    if roll < 0.5:
        return "Catcher", "C"
    if roll < 0.75:
        return "Infielder", "Utility"
    return "Outfielder", "Utility"


def _ensure_physical_stats(stats: dict) -> None:
    if 'height_cm' not in stats:
        stats['height_cm'] = rng.randint(168, 185)
    if 'height_potential' not in stats:
        stats['height_potential'] = stats['height_cm'] + rng.randint(5, 18)
    if 'weight_kg' not in stats:
        stats['weight_kg'] = rng.randint(60, 92)


def _apply_focus_bias(stats: dict, position: str, specific_pos: str, focus: str) -> None:
    """Nudges generated recruits toward their school's stated philosophy."""
    focus_key = (focus or "Balanced").lower()
    is_pitcher = position == "Pitcher"
    is_catcher = position == "Catcher" or specific_pos == "C"

    if focus_key == "power" and not is_pitcher:
        _boost_stat(stats, "power", (8, 14))
        _boost_stat(stats, "contact", (2, 6))
    elif focus_key == "contact" and not is_pitcher:
        _boost_stat(stats, "contact", (8, 14))
        _boost_stat(stats, "speed", (3, 6))
    elif focus_key == "speed" and not is_pitcher:
        _boost_stat(stats, "speed", (10, 16))
        _boost_stat(stats, "fielding", (3, 6))
    elif focus_key == "defense" and not is_pitcher:
        _boost_stat(stats, "fielding", (8, 14))
        _boost_stat(stats, "throwing", (5, 9))
    elif focus_key == "core" and not is_pitcher:
        _boost_stat(stats, "power", (5, 9))
        _boost_stat(stats, "contact", (5, 9))
    elif focus_key == "pitching" and is_pitcher:
        _boost_stat(stats, "velocity", (5, 9), cap=170, default=stats.get("velocity", 132))
        _boost_stat(stats, "control", (5, 9))
        _boost_stat(stats, "movement", (4, 7))
    elif focus_key == "battery":
        if is_pitcher:
            _boost_stat(stats, "control", (4, 7))
            _boost_stat(stats, "movement", (3, 6))
        if is_catcher:
            _boost_stat(stats, "fielding", (6, 11))
            _boost_stat(stats, "throwing", (6, 11))
            _boost_stat(stats, "command", (4, 7))
    elif focus_key == "technical":
        if is_pitcher:
            _boost_stat(stats, "control", (5, 8))
        else:
            _boost_stat(stats, "contact", (5, 8))
            _boost_stat(stats, "discipline", (4, 7))
    elif focus_key == "stamina":
        _boost_stat(stats, "stamina", (10, 18), cap=140, default=stats.get("stamina", 55))
    elif focus_key == "ace" and is_pitcher:
        _boost_stat(stats, "velocity", (8, 12), cap=175, default=stats.get("velocity", 135))
        _boost_stat(stats, "control", (6, 10))
        _boost_stat(stats, "stamina", (12, 20), cap=150, default=stats.get("stamina", 60))
    elif focus_key == "guts":
        _boost_stat(stats, "mental", (5, 10), default=stats.get("mental", 60))
        _boost_stat(stats, "clutch", (6, 12), default=stats.get("clutch", 60))
    elif focus_key == "mental":
        _boost_stat(stats, "discipline", (6, 12), default=stats.get("discipline", 60))
        _boost_stat(stats, "mental", (6, 12), default=stats.get("mental", 65))
    elif focus_key == "random":
        pool = ["velocity", "control", "movement", "stamina"] if is_pitcher else [
            "contact",
            "power",
            "speed",
            "fielding",
            "throwing",
        ]
        boosts = rng.sample(pool, k=min(2, len(pool)))
        for attr in boosts:
            cap = 175 if attr == "velocity" else 150 if attr == "stamina" else 99
            _boost_stat(stats, attr, (6, 12), cap=cap, default=stats.get(attr, 50))


def _boost_stat(stats: dict, key: str, boost_range: tuple[int, int], cap: int = 99, default: int = 50) -> None:
    """Helper to clamp boosted attributes within a safe range."""
    low, high = boost_range
    current = stats.get(key, default)
    stats[key] = min(cap, max(0, int(current + rng.randint(low, high))))


def _grow_height(player: Player) -> int:
    try:
        if player.year not in (2, 3):
            return 0
        current = getattr(player, 'height_cm', None)
        potential = getattr(player, 'height_potential', None)
        if current is None or potential is None:
            return 0

        remaining = max(0, potential - current)
        if remaining <= 0:
            return 0

        tag = getattr(player, 'growth_tag', 'Normal')
        if tag == 'Limitless':
            gain = rng.randint(2, 7)
        elif tag == 'Sleeping Giant':
            gain = rng.randint(0, 10)
        elif tag == 'Grinder':
            gain = rng.randint(1, 3)
        else:
            gain = rng.randint(1, 5)

        height_gain = min(gain, remaining)
        setattr(player, 'height_cm', current + height_gain)
        return height_gain
    except Exception:
        return 0


def _grow_weight(player: Player, height_gain: int) -> None:
    if not hasattr(player, 'weight_kg'):
        return

    current = getattr(player, 'weight_kg', 0) or 0
    pot = getattr(player, 'potential_grade', 'C')
    tag = getattr(player, 'growth_tag', 'Normal')

    base_gain = rng.randint(0, 2)
    if height_gain > 0:
        base_gain += max(1, height_gain // 2)

    if pot in ('S', 'A'):
        base_gain += 1
    if tag == 'Limitless':
        base_gain += 1
    elif tag == 'Sleeping Giant':
        base_gain += rng.randint(0, 2)
    elif tag == 'Grinder':
        base_gain = max(0, base_gain - 1)

    setattr(player, 'weight_kg', min(140, current + base_gain))


def _grow_attributes(player: Player) -> None:
    for attr in BASE_ATTRIBUTES:
        if not hasattr(player, attr):
            continue
        current = getattr(player, attr) or 0
        pot = getattr(player, 'potential_grade', 'C')

        if pot == 'S':
            gain = rng.randint(2, 6)
        elif pot == 'A':
            gain = rng.randint(2, 5)
        elif pot == 'B':
            gain = rng.randint(1, 4)
        elif pot == 'C':
            gain = rng.randint(1, 3)
        else:
            gain = rng.randint(0, 2)

        tag = getattr(player, 'growth_tag', 'Normal')
        if tag == 'Limitless':
            gain = int(gain * 1.4)
        elif tag == 'Sleeping Giant':
            gain = int(gain * rng.uniform(0.7, 2.0))
        elif tag == 'Grinder':
            gain = int(gain * 0.8)

        if player.position == 'Catcher' and attr == 'command':
            gain = int(gain * 1.1)

        try:
            setattr(player, attr, min(99, current + max(0, gain)))
        except Exception:
            continue


def _grow_pitcher_velocity(player: Player) -> None:
    try:
        gain = rng.randint(0, 3)
        if getattr(player, 'growth_tag', '') == 'Limitless':
            gain += 1
        if getattr(player, 'potential_grade', '') == 'S':
            gain += 1
        player.velocity = min(170, (player.velocity or 0) + gain)
    except Exception:
        pass
