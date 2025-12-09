"""Enhanced player profile and scouting renderers.

This module centralises the presentation logic for player-focused screens
and fog-of-war styled opponent scouting reports so the rest of the game can
reuse a consistent look and feel.
"""
from __future__ import annotations

import random
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func

from database.setup_db import Coach, Player, PlayerGameStats, School
from game.mechanics.pitch_mastery import mastery_progress
from ui.ui_display import Colour
from core.event_bus import EventBus

BOX_WIDTH = 78
BAR_WIDTH = 18
ROLE_PRIORITY = [
    "ACE",
    "CAPTAIN",
    "CLEANUP",
    "LEADOFF",
    "CLOSER",
    "STARTER",
    "BENCH",
    "UTILITY",
    "TWO-WAY",
]

TRAIT_DESCRIPTIONS = {
    "Clutch Hitter": "Boosts contact/power in high leverage late innings.",
    "Mental Wall": "Resists momentum loss after errors.",
    "Cheetah": "Elite acceleration on the bases.",
    "Power Hitter": "Higher chance of extra-base hits.",
    "Gold Glove": "Superior defensive range and reactions.",
    "Strikeout King": "Dominates hitters with Ks.",
    "Injury Prone": "Elevated injury risk during heavy weeks.",
}

GRADE_BUCKETS: Sequence[Tuple[int, str]] = (
    (92, "S"),
    (82, "A"),
    (70, "B"),
    (60, "C"),
    (50, "D"),
    (40, "E"),
    (0, "F"),
)


# Minimum 'fame' required for a coach to earn a legendary nickname.
# Uses scouting_ability (0-100). 80 ≈ top decile.
TITLE_THRESHOLD = 80


def _clamp(val: Optional[float], low: int = 0, high: int = 100) -> int:
    if val is None:
        return low
    return max(low, min(high, int(val)))


def generate_coach_title(coach, school: Optional[School] = None) -> Optional[str]:
    """Generate an anime-style legendary coach title using persona, archetype, and location.

    Returns None for coaches below the fame threshold so only elite coaches get a nickname.
    """
    rating = getattr(coach, "scouting_ability", 50) or 50
    if rating < TITLE_THRESHOLD:
        return None

    persona = getattr(coach, "personality", "Stoic") or "Stoic"
    archetype = (getattr(coach, "archetype", "TRADITIONALIST") or "TRADITIONALIST").upper()

    location = "the Diamond"
    if school and getattr(school, "prefecture", None):
        location = school.prefecture

    descriptors = {
        "Gruff": [("Iron", "adj"), ("Grizzled", "adj"), ("Unsmiling", "adj"), ("Old", "adj")],
        "Strict": [("Devil", "adj"), ("Demon", "adj"), ("Steel", "noun_of"), ("Absolute", "adj")],
        "Ruthless": [("Cold", "adj"), ("Ice", "noun_of"), ("Bloodless", "adj"), ("Silent", "adj")],
        "Intense": [("Raging", "adj"), ("Fighting", "adj"), ("Shura", "noun_of"), ("Berserk", "adj")],
        "Stoic": [("Silent", "adj"), ("Stone", "adj"), ("Immovable", "adj"), ("Quiet", "adj")],
        "Logical": [("Data", "adj"), ("Precision", "noun_of"), ("Digital", "adj"), ("Calculated", "adj")],
        "Tactical": [("Trickster", "adj"), ("Cunning", "adj"), ("Shadow", "adj"), ("Magic", "noun_of")],
        "Observant": [("Eagle", "adj"), ("All-Seeing", "adj"), ("Clairvoyant", "adj"), ("Insight", "noun_of")],
        "Serene": [("Smiling", "adj"), ("Sleeping", "adj"), ("Tranquil", "adj"), ("Buddha", "noun_of")],
        "Passionate": [("Roaring", "adj"), ("Crimson", "adj"), ("Burning", "adj"), ("Flame", "noun_of")],
        "Energetic": [("Lightning", "noun_of"), ("Flash", "noun_of"), ("Speed", "noun_of"), ("Rocket", "adj")],
        "Maverick": [("Rogue", "adj"), ("Gambling", "adj"), ("Wild", "adj"), ("Lone", "adj")],
        "Unorthodox": [("Strange", "adj"), ("Mystery", "noun_of"), ("Chaos", "noun_of"), ("Miracle", "noun_of")],
        "Whimsical": [("Dreaming", "adj"), ("Laughing", "adj"), ("Phantom", "adj"), ("Joker", "adj")],
        "Charismatic": [("Golden", "adj"), ("Star", "noun_of"), ("Radiant", "adj"), ("Crownless", "adj")],
        "Mentorly": [("Great", "adj"), ("Big", "adj"), ("Trusted", "adj"), ("Father", "noun_of")],
        "Old-School": [("Legendary", "adj"), ("Ancient", "adj"), ("Showa", "adj"), ("Immortal", "adj")],
        "Philosophical": [("Wise", "adj"), ("Deep", "adj"), ("Sage", "adj"), ("Truth", "noun_of")],
    }

    nouns = {
        "TRADITIONALIST": ["Shogun", "General", "Wall", "Fortress", "Guardian"],
        "INNOVATOR": ["Architect", "Revolutionary", "Pioneer", "Creator"],
        "SCIENTIST": ["Computer", "Professor", "Brain", "Machine"],
        "TACTICIAN": ["Magician", "Fox", "Schemer", "Spider", "Chessmaster"],
        "MOTIVATOR": ["Spirit", "Soul", "Commander", "Captain"],
        "SLUGGER_GURU": ["Monster", "Ogre", "Titan", "Beast", "Cannon"],
        "TALENT_ENGINEER": ["Alchemist", "Gardener", "Teacher", "Sculptor"],
        "BALANCED": ["Ruler", "King", "Emperor", "Director"],
        "MENTOR": ["Sensei", "Master", "Sage", "Hermit"],
    }

    headlines = {
        ("Strict", "TRADITIONALIST"): "The Tyrant",
        ("Ruthless", "BALANCED"): "The Demon King",
        ("Intense", "SLUGGER_GURU"): "The Red Ogre",
        ("Maverick", "TACTICIAN"): f"The Wolf of {location}",
        ("Passionate", "MOTIVATOR"): "The Roaring Soul",
        ("Stoic", "SCIENTIST"): "The Ice Machine",
        ("Unorthodox", "INNOVATOR"): "The Alien",
        ("Serene", "MENTOR"): "The Smiling Buddha",
        ("Whimsical", "TACTICIAN"): "The Magician",
        ("Old-School", "TRADITIONALIST"): "The Fossil",
        ("Energetic", "SLUGGER_GURU"): "The Demon Child",
        ("Strict", "TALENT_ENGINEER"): "The God-Father",
    }

    if (persona, archetype) in headlines:
        return headlines[(persona, archetype)]

    desc_list = descriptors.get(persona, [("Famous", "adj")])
    noun_list = nouns.get(archetype, ["Manager"])
    word, grammar_type = random.choice(desc_list)
    role = random.choice(noun_list)

    use_location = random.random() < 0.30

    if grammar_type == "noun_of":
        return f"The {role} of {word}"

    if grammar_type == "adj":
        if use_location:
            return f"The {word} {role} of {location}"
        return f"The {word} {role}"

    return f"The {word} {role}"


def color_for_value(value: Optional[int]) -> str:
    if value is None:
        return Colour.RESET
    if value < 50:
        return Colour.RED
    if value < 70:
        return Colour.YELLOW
    if value < 90:
        return Colour.CYAN
    return Colour.GREEN


def colored_bar(value: Optional[int], max_value: int = 100) -> str:
    if value is None:
        return Colour.RED + ("?" * BAR_WIDTH) + Colour.RESET
    pct = max(0, min(max_value, value)) / max_value
    filled = int(pct * BAR_WIDTH)
    pad = BAR_WIDTH - filled
    col = color_for_value(value)
    return f"{col}{'█' * filled}{'░' * pad}{Colour.RESET}"


def _stat_bar(value: Optional[int], width: int = BAR_WIDTH, *, max_value: int = 100) -> str:
    if value is None:
        return " " * width
    pct = max(0, min(max_value, value)) / max_value
    filled = int(pct * width)
    return ("█" * filled) + ("▒" * (width - filled))


def _fmt_arrow(delta: Optional[int]) -> str:
    if not delta:
        return "→"
    return f"{Colour.GREEN}↑{Colour.RESET}" if delta > 0 else f"{Colour.RED}↓{Colour.RESET}"


def _grade_label(value: int) -> str:
    for threshold, label in GRADE_BUCKETS:
        if value >= threshold:
            return label
    return "F"


def _grade_range(value: Optional[int]) -> str:
    if value is None:
        return "??"
    if value >= 82:
        return "A?"
    if value >= 70:
        return "B–A?"
    if value >= 60:
        return "C–B"
    if value >= 50:
        return "D–C"
    return "E–D"


def _mask_name(full_name: Optional[str]) -> str:
    if not full_name:
        return "??"
    parts = full_name.split()
    if not parts:
        return "??"
    return ".".join(p[0] for p in parts if p) + "."


def _fetch_traits(player: Player) -> List[str]:
    names: List[str] = []
    for skill in getattr(player, "skills", []) or []:
        label = getattr(skill, "skill_key", "")
        if not label:
            continue
        names.append(label.replace("_", " ").title())
    return names


def _fetch_personality(player: Player) -> Dict[str, int]:
    return {
        "archetype": getattr(player, "archetype", "Balanced") or "Balanced",
        "Leadership": _clamp(getattr(player, "drive", 50)),
        "Composure": _clamp(getattr(player, "discipline", 50)),
        "Coachability": _clamp(100 - getattr(player, "volatility", 50)),
        "Work Ethic": _clamp(getattr(player, "loyalty", 50)),
    }


def _fetch_season_stats(session, player: Player) -> Dict[str, Optional[float]]:
    stats = (
        session.query(
            func.count(PlayerGameStats.game_id).label("games"),
            func.sum(PlayerGameStats.innings_pitched).label("ip"),
            func.sum(PlayerGameStats.strikeouts).label("k"),
            func.sum(PlayerGameStats.walks).label("bb"),
            func.sum(PlayerGameStats.runs_allowed).label("ra"),
            func.sum(PlayerGameStats.at_bats).label("ab"),
            func.sum(PlayerGameStats.hits_batted).label("hits"),
            func.sum(PlayerGameStats.rbi).label("rbi"),
            func.sum(PlayerGameStats.homeruns).label("hr"),
            func.sum(PlayerGameStats.runs).label("runs_scored"),
        )
        .filter(PlayerGameStats.player_id == player.id)
        .one()
    )
    ip = stats.ip or 0
    era = round((stats.ra * 9) / ip, 2) if ip else None
    ab = stats.ab or 0
    avg = round((stats.hits or 0) / ab, 3) if ab else None
    return {
        "games": stats.games,
        "era": era,
        "ip": ip,
        "k": stats.k,
        "bb": stats.bb,
        "runs_allowed": stats.ra,
        "avg": avg,
        "ab": ab,
        "hits": stats.hits,
        "rbi": stats.rbi,
        "hr": stats.hr,
        "runs_scored": stats.runs_scored,
    }


def _gather_player_data(session, player_id: int) -> Optional[Dict]:
    player = session.get(Player, player_id)
    if not player:
        return None
    school = session.get(School, player.school_id) if player.school_id else None
    return {
        "player": player,
        "school": school,
        "traits": _fetch_traits(player),
        "personality": _fetch_personality(player),
        "season_stats": _fetch_season_stats(session, player),
        "deltas": getattr(player, "delta_stats", {}) or {},
    }


def _emit_profile_event(
    event_bus: Optional[EventBus],
    event_sink: Optional[List[Dict[str, Any]]],
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    event = {"type": event_type, "payload": payload}
    if event_sink is not None:
        event_sink.append(event)
    if event_bus:
        event_bus.publish(event_type, payload)


def _header_block(title: str, subtitle: str) -> List[str]:
    lines = [
        Colour.CYAN + "═" * BOX_WIDTH + Colour.RESET,
        title.center(BOX_WIDTH),
    ]
    if subtitle:
        lines.append(Colour.YELLOW + subtitle.center(BOX_WIDTH) + Colour.RESET)
    lines.append(Colour.CYAN + "═" * BOX_WIDTH + Colour.RESET)
    return lines


def _profile_summary(data: Dict) -> List[str]:
    player: Player = data["player"]
    school = data["school"]
    display_name = " ".join(part for part in [getattr(player, "last_name", ""), getattr(player, "first_name", "")] if part).strip() or player.name
    summary = f"{player.position or '??'} | Year {player.year or '?'}"
    if getattr(player, "height_cm", None):
        summary += f" | {player.height_cm} cm"
    if getattr(player, "weight_kg", None):
        summary += f" / {player.weight_kg} kg"
    lines = _header_block((display_name or player.name).upper(), summary)
    school_name = school.name if school else "Free Agent"
    lines.append(f"School: {school_name}")
    roles = []
    if getattr(player, "is_captain", False):
        roles.append("CAPTAIN")
    if player.position == "Pitcher" and (player.velocity or 0) >= 140:
        roles.append("ACE")
    if getattr(player, "is_two_way", False):
        roles.append("TWO-WAY")
    if getattr(player, "role", None):
        roles.append(player.role.upper())
    ordered = [role for role in ROLE_PRIORITY if role in roles]
    lines.append(f"Roles: {', '.join(ordered) if ordered else 'None'}")
    if player.position == "Pitcher":
        slot = getattr(player, "arm_slot", None) or "Three-Quarters"
        lines.append(f"Arm Slot: {slot}")
    lines.append("─" * BOX_WIDTH)
    return lines


def _render_attribute_rows(data: Dict, knowledge_level: int) -> List[str]:
    player: Player = data["player"]
    deltas = data["deltas"]
    lines: List[str] = []
    show_pitching = player.position == "Pitcher" or getattr(player, "is_two_way", False)
    show_fielding = player.position != "Pitcher" or getattr(player, "is_two_way", False)
    if show_pitching:
        lines.append(f"{Colour.GOLD}[ Pitching ]{Colour.RESET}")
        rows = [
            ("Velocity", player.velocity, deltas.get("velocity")),
            ("Control", player.control, deltas.get("control")),
            ("Command", player.command, deltas.get("command")),
            ("Movement", player.movement, deltas.get("movement")),
            ("Stamina", player.stamina, deltas.get("stamina")),
        ]
        for label, value, delta in rows:
            display = value if knowledge_level >= 3 else None if knowledge_level == 0 else value
            max_value = 160 if label == "Velocity" else 100
            bar = _stat_bar(display or 0, max_value=max_value)
            val_txt = "--" if display is None else f"{int(display):>3}"
            lines.append(f"{label:<10} {bar}  {val_txt}  {_fmt_arrow(delta)}")
        lines.append("")
    if show_fielding:
        lines.append(f"{Colour.GOLD}[ Batting / Fielding ]{Colour.RESET}")
        rows = [
            ("Contact", player.contact, deltas.get("contact")),
            ("Power", player.power, deltas.get("power")),
            ("Speed", player.speed, deltas.get("speed")),
            ("Fielding", player.fielding, deltas.get("fielding")),
            ("Throwing", player.throwing, deltas.get("throwing")),
        ]
        if (player.position or "").lower() == "catcher":
            rows.append(("Wall", getattr(player, "catcher_ability", None), deltas.get("catcher_ability")))
        for label, value, delta in rows:
            display = value if knowledge_level >= 2 else None if knowledge_level == 0 else value
            bar = _stat_bar(display or 0)
            val_txt = "--" if display is None else f"{int(display):>3}"
            lines.append(f"{label:<10} {bar}  {val_txt}  {_fmt_arrow(delta)}")
        lines.append("")
    return lines


def _render_pitch_repertoire(player: Player, knowledge_level: int) -> List[str]:
    lines: List[str] = []
    if player.position != "Pitcher" and not getattr(player, "is_two_way", False):
        return lines
    pitches = getattr(player, "pitch_repertoire", []) or []
    lines.append(f"{Colour.GOLD}[ Pitch Repertoire ]{Colour.RESET}")
    if not pitches:
        lines.append("  --")
        return lines
    for pitch in pitches:
        name = getattr(pitch, "pitch_name", "Unnamed")
        quality = getattr(pitch, "quality", "--") if knowledge_level >= 3 else "--"
        break_level = getattr(pitch, "break_level", "--") if knowledge_level >= 3 else "--"
        xp = getattr(pitch, "mastery_xp", 0)
        level, next_xp = mastery_progress(xp)
        level_txt = "Lv ?" if knowledge_level == 0 else f"Lv {level}"
        if knowledge_level >= 3 and next_xp is not None:
            level_txt = f"Lv {level} ({xp}/{next_xp})"
        lines.append(f"  {name:<18} Grade:{quality}  Break:{break_level}  Mastery:{level_txt}")
    lines.append("")
    return lines


def _render_traits_block(data: Dict, knowledge_level: int) -> List[str]:
    lines: List[str] = []
    traits = data.get("traits") or []
    lines.append(f"{Colour.GOLD}[ Traits ]{Colour.RESET}")
    if not traits:
        lines.append("  No unique traits detected.")
        return lines
    for trait in traits:
        desc = TRAIT_DESCRIPTIONS.get(trait, "") if knowledge_level >= 3 else ""
        if desc:
            lines.append(f"  • {trait}: {desc}")
        else:
            lines.append(f"  • {trait}")
    lines.append("")
    return lines


def _render_personality_block(data: Dict, knowledge_level: int) -> List[str]:
    lines: List[str] = []
    personality = data.get("personality") or {}
    lines.append(f"{Colour.GOLD}[ Personality ]{Colour.RESET}")
    arch = personality.get("archetype", "Balanced")
    lines.append(f"  Archetype: {arch}")
    for key in ("Leadership", "Composure", "Coachability", "Work Ethic"):
        if key not in personality:
            continue
        value = personality[key]
        show = value if knowledge_level >= 2 else None
        bar = _stat_bar(show or 0)
        label = "--" if show is None else f"{show:>3}"
        lines.append(f"  {key:<12} {bar}  {label}")
    lines.append("")
    return lines


def _render_season_stats(data: Dict, knowledge_level: int) -> List[str]:
    lines: List[str] = []
    stats = data.get("season_stats") or {}
    player: Player = data["player"]
    lines.append(f"{Colour.GOLD}[ Season Snapshot ]{Colour.RESET}")
    if stats.get("games") is None:
        lines.append("  No recorded games yet.")
        return lines
    if player.position == "Pitcher":
        if knowledge_level == 0:
            lines.append("  Stats hidden.")
            return lines
        era = stats.get("era")
        ip = stats.get("ip")
        k = stats.get("k")
        bb = stats.get("bb")
        lines.append(f"  ERA: {era if era is not None else '--'} | IP: {ip or '--'} | K: {k or '--'} | BB: {bb or '--'}")
    else:
        if knowledge_level == 0:
            lines.append("  Stats hidden.")
            return lines
        avg = stats.get("avg")
        hr = stats.get("hr")
        rbi = stats.get("rbi")
        runs = stats.get("runs_scored")
        lines.append(f"  AVG: {avg if avg is not None else '--'} | HR: {hr or '--'} | RBI: {rbi or '--'} | R: {runs or '--'}")
    lines.append("")
    return lines


def _build_profile_lines(data: Dict, knowledge_level: int) -> List[str]:
    lines: List[str] = []
    lines.extend(_profile_summary(data))
    lines.extend(_render_attribute_rows(data, knowledge_level))
    lines.extend(_render_pitch_repertoire(data["player"], knowledge_level))
    lines.extend(_render_traits_block(data, knowledge_level))
    lines.extend(_render_personality_block(data, knowledge_level))
    lines.extend(_render_season_stats(data, knowledge_level))
    return lines


def render_player_profile(
    session,
    player_id: int,
    knowledge_level: int = 3,
    *,
    event_bus: Optional[EventBus] = None,
    event_sink: Optional[List[Dict[str, Any]]] = None,
) -> Optional[List[str]]:
    data = _gather_player_data(session, player_id)
    if not data:
        _emit_profile_event(event_bus, event_sink, "PLAYER_PROFILE_ERROR", {"player_id": player_id, "reason": "not_found"})
        return None
    lines = _build_profile_lines(data, knowledge_level)
    _emit_profile_event(
        event_bus,
        event_sink,
        "PLAYER_PROFILE_LINES",
        {"player_id": player_id, "mode": "classic", "knowledge_level": knowledge_level, "lines": lines},
    )
    return lines


def render_player_profile_modern(
    session,
    player_id: int,
    *,
    theme_name: Optional[str] = None,
    fast: bool = False,
    event_bus: Optional[EventBus] = None,
    event_sink: Optional[List[Dict[str, Any]]] = None,
) -> Optional[List[str]]:
    data = _gather_player_data(session, player_id)
    if not data:
        _emit_profile_event(event_bus, event_sink, "PLAYER_PROFILE_ERROR", {"player_id": player_id, "reason": "not_found"})
        return None
    lines = _build_profile_lines(data, knowledge_level=3)
    payload = {
        "player_id": player_id,
        "mode": "modern",
        "theme": theme_name,
        "fast": fast,
        "lines": lines,
    }
    _emit_profile_event(event_bus, event_sink, "PLAYER_PROFILE_LINES", payload)
    return lines


def render_opponent_star_preview(session, player_id: int, knowledge_level: int) -> Optional[List[str]]:
    return render_player_profile(session, player_id, knowledge_level)


# ---------------------------------------------------------------------------
# Team scouting renderer
# ---------------------------------------------------------------------------

def _avg(values: Iterable[Optional[int]]) -> int:
    pool = [v for v in values if isinstance(v, (int, float))]
    if not pool:
        return 40
    return int(sum(pool) / len(pool))


def _compute_team_ratings(players: List[Player], school: School) -> Dict[str, int]:
    offense = _avg([((p.contact or 0) + (p.power or 0)) / 2 for p in players if p.position != "Pitcher"])
    pitching = _avg([((p.velocity or 0) + (p.control or 0)) / 2 for p in players if p.position == "Pitcher"])
    defense = _avg([p.fielding or 0 for p in players])
    speed = _avg([p.speed or 0 for p in players])
    coach = _clamp(getattr(school, "prestige", 50))
    return {
        "offense": offense,
        "pitching": pitching,
        "defense": defense,
        "speed": speed,
        "coach": coach,
    }


def _render_rating_line(label: str, value: int, masked: bool = False) -> str:
    grade = _grade_label(value)
    if masked:
        grade = f"~{grade}?"
    return f"│  {label:<15}{colored_bar(value)}  {grade:<6}│"


def _build_masked_roster(players: List[Player]) -> List[Dict]:
    roster = []
    for player in players[:9]:
        entry = {
            "jersey": player.jersey_number or "--",
            "pos": (player.position or "--")[:3],
            "masked_name": _mask_name(player.name),
        }
        if player.position == "Pitcher":
            entry["attr_1"] = f"Vel { _grade_range(player.velocity)}"
            entry["attr_2"] = f"Ctl { _grade_range(player.control)}"
            entry["attr_3"] = f"Sta { _grade_range(player.stamina)}"
        else:
            entry["attr_1"] = f"Con { _grade_range(player.contact)}"
            entry["attr_2"] = f"Pow { _grade_range(player.power)}"
            entry["attr_3"] = f"Spd { _grade_range(player.speed)}"
        roster.append(entry)
    return roster


def _build_full_roster(players: List[Player]) -> List[Dict]:
    roster = []
    for player in players[:12]:
        roster.append(
            {
                "jersey": player.jersey_number or "--",
                "pos": (player.position or "--")[:3],
                "name": player.name,
                "velocity": player.velocity,
                "control": player.control,
                "movement": player.movement,
                "contact": player.contact,
                "power": player.power,
                "speed": player.speed,
                "throwing": player.throwing,
            }
        )
    return roster


def _build_tendencies(players: List[Player], ratings: Dict[str, int]) -> Dict[str, List[str]]:
    tendencies = {
        "offense": [],
        "pitching": [],
        "strengths": [],
        "weaknesses": [],
    }
    if ratings["offense"] >= 70:
        tendencies["strengths"].append("Lineup can trade blows with anyone.")
    if ratings["pitching"] >= 70:
        tendencies["strengths"].append("Rotation features legitimate front-line stuff.")
    if ratings["defense"] < 55:
        tendencies["weaknesses"].append("Glove work is suspect; apply pressure on balls in play.")
    if ratings["speed"] < 55:
        tendencies["weaknesses"].append("Running game lacks punch; outfield can shade deep.")
    if not tendencies["strengths"]:
        tendencies["strengths"].append("Balanced roster; no glaring elite trait.")
    if not tendencies["weaknesses"]:
        tendencies["weaknesses"].append("Scouting reports show no major weakness.")
    tendencies["offense"].append(
        "Aggressive on first pitch" if ratings["offense"] >= 65 else "Prefers to work counts"
    )
    tendencies["pitching"].append(
        "Leans on velocity more than finesse" if ratings["pitching"] >= 65 else "Crafty staff built on command"
    )
    return tendencies


def render_team_scouting_report(
    session,
    school_id: int,
    scouting_level: int,
    rivalry_score: int = 0,
    *,
    event_bus: Optional[EventBus] = None,
    event_sink: Optional[List[Dict[str, Any]]] = None,
) -> Optional[List[str]]:
    school = session.get(School, school_id)
    if not school:
        _emit_profile_event(event_bus, event_sink, "TEAM_SCOUTING_ERROR", {"school_id": school_id, "reason": "not_found"})
        return None
    level = max(0, min(3, scouting_level))
    if rivalry_score >= 80 and level > 0:
        level -= 1
    players = (
        session.query(Player)
        .filter(Player.school_id == school.id)
        .order_by(Player.jersey_number.is_(None), Player.jersey_number)
        .all()
    )
    ratings = _compute_team_ratings(players, school)
    masked_roster = _build_masked_roster(players)
    full_roster = _build_full_roster(players)
    tendencies = _build_tendencies(players, ratings)

    lines: List[str] = []
    lines.append("═" * BOX_WIDTH)
    lines.append(f"TARGET: {school.name} | Prefecture: {school.prefecture}".center(BOX_WIDTH))
    lines.append("═" * BOX_WIDTH)
    coach = getattr(school, "coach", None)
    if coach:
        title = generate_coach_title(coach, school)
        persona = getattr(coach, "personality", "?")
        archetype = getattr(coach, "archetype", "?")
        name = getattr(coach, 'name', 'Coach')
        suffix = f" — {title}" if title else ""
        lines.append(f"Coach: {name}{suffix} ({persona} / {archetype})")
        lines.append("")
    if level == 0:
        lines.append("[ FOG OF WAR ] No intel. Purchase scouting to unlock data.")
    elif level == 1:
        lines.append("[ BASIC ESTIMATES ]")
        lines.append(_render_rating_line("Offense", ratings["offense"], masked=True))
        lines.append(_render_rating_line("Pitching", ratings["pitching"], masked=True))
        lines.append(_render_rating_line("Defense", ratings["defense"], masked=True))
        lines.append(_render_rating_line("Speed", ratings["speed"], masked=True))
        lines.append(_render_rating_line("Coaching IQ", ratings["coach"], masked=True))
        lines.append("")
        lines.append("Roster intel locked.")
    elif level == 2:
        lines.append("[ PARTIAL ROSTER ]")
        for entry in masked_roster:
            attrs = f"{entry['attr_1']} | {entry['attr_2']} | {entry['attr_3']}"
            lines.append(f"#{entry['jersey']:>2} {entry['pos']:<3} {entry['masked_name']:<8}  {attrs}")
        lines.append("")
        lines.append("Team Tendencies:")
        for line in tendencies["offense"] + tendencies["pitching"]:
            lines.append(f"  • {line}")
    else:
        lines.append("[ FULL INTEL ]")
        for entry in full_roster:
            if entry["pos"] == "Pit":
                attrs = f"VEL {entry['velocity']} | CTL {entry['control']} | MOV {entry['movement']}"
            else:
                attrs = f"CON {entry['contact']} | POW {entry['power']} | SPD {entry['speed']}"
            highlight = Colour.RED if (entry['pos'] == 'Pit' and entry['velocity'] and entry['velocity'] >= 150) else ""
            reset = Colour.RESET if highlight else ""
            lines.append(f"#{entry['jersey']:>2} {entry['pos']:<3} {highlight}{entry['name']:<20}{reset} {attrs}")
        lines.append("")
        lines.append("Matchup Notes:")
        for line in tendencies["strengths"]:
            lines.append(f"  ✓ {line}")
        for line in tendencies["weaknesses"]:
            lines.append(f"  ⚠ {line}")
    lines.append("")
    lines.append(f"Fog level: {["BLACKOUT", "BASIC", "MASKED", "FULL"][level]}")
    _emit_profile_event(
        event_bus,
        event_sink,
        "TEAM_SCOUTING_REPORT",
        {
            "school_id": school_id,
            "scouting_level": level,
            "rivalry_score": rivalry_score,
            "lines": lines,
        },
    )
    return lines


# ---------------------------------------------------------------------------
# Coach profile renderer
# ---------------------------------------------------------------------------


def _render_coach_slider(label: str, value: float) -> str:
    pct = _clamp(value * 100 if value <= 1 else value)
    bar = _stat_bar(pct)
    return f"  {label:<12} {bar}  {pct:>3}"


def render_coach_profile(session, coach_id: int, knowledge_level: int = 3) -> Optional[List[str]]:
    coach = session.get(Coach, coach_id)
    if not coach:
        return None
    school = session.get(School, coach.school_id) if coach.school_id else None

    name = getattr(coach, "name", "Coach") or "Coach"
    title = generate_coach_title(coach, school)
    persona = getattr(coach, "personality", "?")
    archetype = getattr(coach, "archetype", "?")

    lines: List[str] = []
    subtitle = title or ""
    lines.extend(_header_block(name.upper(), subtitle))
    if school:
        lines.append(f"School: {school.name} ({school.prefecture})")
    lines.append(f"Persona: {persona} | Archetype: {archetype}")
    lines.append("─" * BOX_WIDTH)

    # Emotional sliders
    lines.append(f"{Colour.GOLD}[ Traits ]{Colour.RESET}")
    lines.append(_render_coach_slider("Drive", getattr(coach, "drive", 50)))
    lines.append(_render_coach_slider("Loyalty", getattr(coach, "loyalty", 50)))
    lines.append(_render_coach_slider("Volatility", getattr(coach, "volatility", 50)))
    lines.append("")

    lines.append(f"{Colour.GOLD}[ Philosophy ]{Colour.RESET}")
    lines.append(_render_coach_slider("Tradition", getattr(coach, "tradition", 0.5)))
    lines.append(_render_coach_slider("Logic", getattr(coach, "logic", 0.5)))
    lines.append(_render_coach_slider("Temper", getattr(coach, "temper", 0.5)))
    lines.append(_render_coach_slider("Ambition", getattr(coach, "ambition", 0.5)))
    lines.append("")

    lines.append(f"{Colour.GOLD}[ Tools ]{Colour.RESET}")
    lines.append(_render_coach_slider("Scouting", getattr(coach, "scouting_ability", 50)))
    lines.append(_render_coach_slider("Seniority Wt", getattr(coach, "seniority_weight", 0.5)))
    lines.append(_render_coach_slider("Trust Wt", getattr(coach, "trust_weight", 0.5)))
    lines.append(_render_coach_slider("Stats Wt", getattr(coach, "stats_weight", 0.5)))
    lines.append(_render_coach_slider("Fatigue Pen", getattr(coach, "fatigue_penalty_weight", 0.5)))
    lines.append("")

    return lines
