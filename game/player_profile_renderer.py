"""Enhanced player profile and scouting renderers.

This module centralises the presentation logic for player-focused screens
and fog-of-war styled opponent scouting reports so the rest of the game can
reuse a consistent look and feel.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func

from database.setup_db import Player, PlayerGameStats, School
from ui.ui_display import Colour, clear_screen
from ui.ui_core import (
    BAR_WIDTH as UI_BAR_WIDTH,
    choose_theme,
    colored_bar as ui_colored_bar,
    simple_bar as ui_simple_bar,
    slide_in_panel,
)

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


def _clamp(val: Optional[float], low: int = 0, high: int = 100) -> int:
    if val is None:
        return low
    return max(low, min(high, int(val)))


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


def _stat_bar(value: Optional[int], width: int = BAR_WIDTH) -> str:
    if value is None:
        return " " * width
    pct = max(0, min(100, value)) / 100
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


def _header_block(title: str, subtitle: str) -> None:
    print(Colour.CYAN + "═" * BOX_WIDTH + Colour.RESET)
    print(title.center(BOX_WIDTH))
    if subtitle:
        print(Colour.YELLOW + subtitle.center(BOX_WIDTH) + Colour.RESET)
    print(Colour.CYAN + "═" * BOX_WIDTH + Colour.RESET)


def _profile_summary(data: Dict) -> None:
    player: Player = data["player"]
    school = data["school"]
    summary = f"{player.position or '??'} | Year {player.year or '?'}"
    if getattr(player, "height_cm", None):
        summary += f" | {player.height_cm} cm"
    if getattr(player, "weight_kg", None):
        summary += f" / {player.weight_kg} kg"
    _header_block(player.name.upper(), summary)
    school_name = school.name if school else "Free Agent"
    print(f"School: {school_name}")
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
    print(f"Roles: {', '.join(ordered) if ordered else 'None'}")
    print("─" * BOX_WIDTH)


def _render_attribute_rows(data: Dict, knowledge_level: int) -> None:
    player: Player = data["player"]
    deltas = data["deltas"]
    show_pitching = player.position == "Pitcher" or getattr(player, "is_two_way", False)
    show_fielding = player.position != "Pitcher" or getattr(player, "is_two_way", False)
    if show_pitching:
        print(f"{Colour.GOLD}[ Pitching ]{Colour.RESET}")
        rows = [
            ("Velocity", player.velocity, deltas.get("velocity")),
            ("Control", player.control, deltas.get("control")),
            ("Command", player.command, deltas.get("command")),
            ("Movement", player.movement, deltas.get("movement")),
            ("Stamina", player.stamina, deltas.get("stamina")),
        ]
        for label, value, delta in rows:
            display = value if knowledge_level >= 3 else None if knowledge_level == 0 else value
            bar = _stat_bar(display or 0)
            val_txt = "--" if display is None else f"{int(display):>3}"
            print(f"{label:<10} {bar}  {val_txt}  {_fmt_arrow(delta)}")
        print()
    if show_fielding:
        print(f"{Colour.GOLD}[ Batting / Fielding ]{Colour.RESET}")
        rows = [
            ("Contact", player.contact, deltas.get("contact")),
            ("Power", player.power, deltas.get("power")),
            ("Speed", player.speed, deltas.get("speed")),
            ("Fielding", player.fielding, deltas.get("fielding")),
            ("Throwing", player.throwing, deltas.get("throwing")),
        ]
        for label, value, delta in rows:
            display = value if knowledge_level >= 2 else None if knowledge_level == 0 else value
            bar = _stat_bar(display or 0)
            val_txt = "--" if display is None else f"{int(display):>3}"
            print(f"{label:<10} {bar}  {val_txt}  {_fmt_arrow(delta)}")
        print()


def _render_pitch_repertoire(player: Player, knowledge_level: int) -> None:
    if player.position != "Pitcher" and not getattr(player, "is_two_way", False):
        return
    pitches = getattr(player, "pitch_repertoire", []) or []
    print(f"{Colour.GOLD}[ Pitch Repertoire ]{Colour.RESET}")
    if not pitches:
        print("  --")
        return
    for pitch in pitches:
        name = getattr(pitch, "pitch_name", "Unnamed")
        quality = getattr(pitch, "quality", "--") if knowledge_level >= 3 else "--"
        break_level = getattr(pitch, "break_level", "--") if knowledge_level >= 3 else "--"
        print(f"  {name:<18} Grade:{quality}  Break:{break_level}")
    print()


def _render_traits_block(data: Dict, knowledge_level: int) -> None:
    traits = data.get("traits") or []
    print(f"{Colour.GOLD}[ Traits ]{Colour.RESET}")
    if not traits:
        print("  No unique traits detected.")
        return
    for trait in traits:
        desc = TRAIT_DESCRIPTIONS.get(trait, "") if knowledge_level >= 3 else ""
        if desc:
            print(f"  • {trait}: {desc}")
        else:
            print(f"  • {trait}")
    print()


def _render_personality_block(data: Dict, knowledge_level: int) -> None:
    personality = data.get("personality") or {}
    print(f"{Colour.GOLD}[ Personality ]{Colour.RESET}")
    arch = personality.get("archetype", "Balanced")
    print(f"  Archetype: {arch}")
    for key in ("Leadership", "Composure", "Coachability", "Work Ethic"):
        if key not in personality:
            continue
        value = personality[key]
        show = value if knowledge_level >= 2 else None
        bar = _stat_bar(show or 0)
        label = "--" if show is None else f"{show:>3}"
        print(f"  {key:<12} {bar}  {label}")
    print()


def _render_season_stats(data: Dict, knowledge_level: int) -> None:
    stats = data.get("season_stats") or {}
    player: Player = data["player"]
    print(f"{Colour.GOLD}[ Season Snapshot ]{Colour.RESET}")
    if stats.get("games") is None:
        print("  No recorded games yet.")
        return
    if player.position == "Pitcher":
        if knowledge_level == 0:
            print("  Stats hidden.")
            return
        era = stats.get("era")
        ip = stats.get("ip")
        k = stats.get("k")
        bb = stats.get("bb")
        print(f"  ERA: {era if era is not None else '--'} | IP: {ip or '--'} | K: {k or '--'} | BB: {bb or '--'}")
    else:
        if knowledge_level == 0:
            print("  Stats hidden.")
            return
        avg = stats.get("avg")
        hr = stats.get("hr")
        rbi = stats.get("rbi")
        runs = stats.get("runs_scored")
        print(f"  AVG: {avg if avg is not None else '--'} | HR: {hr or '--'} | RBI: {rbi or '--'} | R: {runs or '--'}")
    print()


def render_player_profile(session, player_id: int, knowledge_level: int = 3) -> None:
    data = _gather_player_data(session, player_id)
    if not data:
        print("Player not found.")
        return
    clear_screen()
    _profile_summary(data)
    _render_attribute_rows(data, knowledge_level)
    _render_pitch_repertoire(data["player"], knowledge_level)
    _render_traits_block(data, knowledge_level)
    _render_personality_block(data, knowledge_level)
    _render_season_stats(data, knowledge_level)
    input(f"\n{Colour.GREEN}[Press Enter to return]{Colour.RESET}")


# ---------------------------------------------------------------------------
# Modern renderer using ui_core primitives (non-breaking alternative)
# ---------------------------------------------------------------------------

def render_player_profile_modern(session, player_id: int, *, theme_name: Optional[str] = None, fast: bool = False) -> None:
    """Render a player profile using the reusable ui_core components.

    Keeps the legacy renderer intact while offering a themeable option for future UI work.
    """

    data = _gather_player_data(session, player_id)
    if not data:
        print("Player not found.")
        return

    player = data["player"]
    school = data["school"]
    traits = data.get("traits", [])
    personality = data.get("personality", {})
    stats = data.get("season_stats", {})

    clear_screen()
    header_lines = [
        f"{player.name} / {player.position or '?'} | Year {getattr(player, 'year', '?')} | {getattr(player, 'height_cm', getattr(player, 'height', '?'))} cm",
        f"School: {getattr(school, 'name', 'Unaffiliated')}"
    ]
    if fast:
        for line in header_lines:
            print(line)
    else:
        slide_in_panel(header_lines, width=78, delay=0.002)

    print("\nATTRIBUTES")
    primary = [
        ("Velocity", getattr(player, "velocity", None)),
        ("Control", getattr(player, "control", None)),
        ("Movement", getattr(player, "movement", None)),
        ("Stamina", getattr(player, "stamina", None)),
    ]
    hitting = [
        ("Contact", getattr(player, "contact", None)),
        ("Power", getattr(player, "power", None)),
        ("Speed", getattr(player, "speed", None)),
        ("Fielding", getattr(player, "fielding", None)),
        ("Throwing", getattr(player, "throwing", None)),
    ]
    for label, val in primary:
        bar = ui_colored_bar(val, 100, theme_name)
        print(f" {label:<10} {bar}  {val if val is not None else '--'}")
    for label, val in hitting:
        bar = ui_colored_bar(val, 100, theme_name)
        print(f" {label:<10} {bar}  {val if val is not None else '--'}")

    print("\nREPERTOIRE")
    repertoire = getattr(player, "pitch_repertoire", []) or []
    if repertoire:
        for pitch in repertoire:
            name = getattr(pitch, "pitch_name", "Pitch")
            q = getattr(pitch, "quality", "--")
            print(f"  • {name} (Grade {q})")
    elif (player.position or "").lower().startswith("pitch"):
        print("  (No pitches recorded)")
    else:
        print("  N/A")

    print("\nTRAITS")
    if not traits:
        print("  (None)")
    else:
        for t in traits:
            desc = TRAIT_DESCRIPTIONS.get(t, "")
            print(f"  • {t}: {desc}")

    print("\nPERSONALITY")
    for key, val in personality.items():
        if key == "archetype":
            print(f"  Archetype: {val}")
            continue
        bar = ui_simple_bar((val * 10) if isinstance(val, (int, float)) and val <= 10 else val, 100, UI_BAR_WIDTH)
        print(f"  {key:<12}: {bar}  {val}")

    print("\nSEASON SNAPSHOT")
    if (player.position or "").lower().startswith("pitch"):
        print(f"  ERA: {stats.get('era', '--')}  IP: {stats.get('ip', '--')}  K: {stats.get('k', '--')}  BB: {stats.get('bb', '--')}")
    else:
        print(f"  AVG: {stats.get('avg', '--')}  HR: {stats.get('hr', '--')}  RBI: {stats.get('rbi', '--')}  R: {stats.get('runs_scored', '--')}")

    print("\n" + "═" * 78)
    input("Press Enter to continue...")


def render_opponent_star_preview(session, player_id: int, knowledge_level: int) -> None:
    render_player_profile(session, player_id, knowledge_level)


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
) -> None:
    school = session.get(School, school_id)
    if not school:
        print("School not found.")
        return
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

    clear_screen()
    print("═" * BOX_WIDTH)
    print(f"TARGET: {school.name} | Prefecture: {school.prefecture}".center(BOX_WIDTH))
    print("═" * BOX_WIDTH)
    if level == 0:
        print("[ FOG OF WAR ] No intel. Purchase scouting to unlock data.")
    elif level == 1:
        print("[ BASIC ESTIMATES ]")
        print(_render_rating_line("Offense", ratings["offense"], masked=True))
        print(_render_rating_line("Pitching", ratings["pitching"], masked=True))
        print(_render_rating_line("Defense", ratings["defense"], masked=True))
        print(_render_rating_line("Speed", ratings["speed"], masked=True))
        print(_render_rating_line("Coaching IQ", ratings["coach"], masked=True))
        print("\nRoster intel locked.")
    elif level == 2:
        print("[ PARTIAL ROSTER ]")
        for entry in masked_roster:
            attrs = f"{entry['attr_1']} | {entry['attr_2']} | {entry['attr_3']}"
            print(f"#{entry['jersey']:>2} {entry['pos']:<3} {entry['masked_name']:<8}  {attrs}")
        print("\nTeam Tendencies:")
        for line in tendencies["offense"] + tendencies["pitching"]:
            print(f"  • {line}")
    else:
        print("[ FULL INTEL ]")
        for entry in full_roster:
            if entry["pos"] == "Pit":
                attrs = f"VEL {entry['velocity']} | CTL {entry['control']} | MOV {entry['movement']}"
            else:
                attrs = f"CON {entry['contact']} | POW {entry['power']} | SPD {entry['speed']}"
            highlight = Colour.RED if (entry['pos'] == 'Pit' and entry['velocity'] and entry['velocity'] >= 150) else ""
            reset = Colour.RESET if highlight else ""
            print(f"#{entry['jersey']:>2} {entry['pos']:<3} {highlight}{entry['name']:<20}{reset} {attrs}")
        print("\nMatchup Notes:")
        for line in tendencies["strengths"]:
            print(f"  ✓ {line}")
        for line in tendencies["weaknesses"]:
            print(f"  ⚠ {line}")
    print("\nFog level:", ["BLACKOUT", "BASIC", "MASKED", "FULL"][level])
    input(f"\n{Colour.GREEN}[Press Enter to return]{Colour.RESET}")
