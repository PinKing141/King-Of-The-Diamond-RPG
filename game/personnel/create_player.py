import sys
import os
import json
import random
import time
import logging
from typing import Optional, List, Tuple, Dict, Any

if os.name == "nt":
    import msvcrt  # Windows-only single-key input
    tty = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]
else:
    import tty
    import termios
    msvcrt = None  # type: ignore[assignment]

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from core.io_interface import IOInterface

# Simple ANSI clear screen to reduce clutter between prompts
CLEAR_SCREEN = "\033[2J\033[H"

# Add repo root to path so sibling packages (core, game, match_engine) resolve in CLI runs.
_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)

from database.setup_db import School, Player, PitchRepertoire
from database.populate_japan import roll_arm_slot
from player_roles.two_way import roll_two_way_profile
from game.systems.academic_system import roll_academic_profile
from game.personnel.relationship_manager import seed_relationships
from game.personnel.personality import roll_player_personality
from game.personnel.player_generation import maybe_assign_bad_trait
from game.mechanics.trait_logic import grant_user_creation_trait_rolls
from game.mechanics.pitch_mastery import mastery_level_for_xp
from game.story.theme_generator import assign_theme_if_eligible
from match_engine.pitch_definitions import PITCH_TYPES

LOGGER = logging.getLogger(__name__)

# --- GROWTH STYLE DEFINITIONS ---
_DEFAULT_GROWTH_STYLE_INFO = {
    # Pitchers
    "Heat Seeker": {
        "desc": "Overwhelm batters with raw velocity and an intimidating presence.",
        "pros": "+Velocity scaling, +Stamina headroom, high fastballs induce whiffs",
        "cons": "-Control develops slowly, punished heavily for mistakes in the zone",
        "detail": "Fastball velocity and Stamina grow rapidly. Control and Command lag behind, meaning early career innings may be wild until you gain experience.",
    },
    "Corner Artist": {
        "desc": "Surgical precision that paints the edges of the strike zone.",
        "pros": "+Control growth, +Command consistency, efficient pitch counts",
        "cons": "-Lower Velocity ceiling, reliant on umpire calls and framing",
        "detail": "Control and Command attributes upgrade cheaper and faster. Velocity gains are minimal, requiring you to rely on location to generate weak contact.",
    },
    "Spin Doctor": {
        "desc": "Master of deception who makes the ball dance away from barrels.",
        "pros": "+Movement scaling, +Break sharpness, excels at strikeouts",
        "cons": "-Stamina drains faster on high-effort pitches, wild pitches common",
        "detail": "Movement and breaking ball quality improve quickly. However, Control can be volatile, and high-break pitches often carry a higher stamina tax.",
    },
    "Balanced Pitcher": {
        "desc": "Jack of all trades who adapts to any rotation spot.",
        "pros": "No glaring weakness, steady gains across all pitching tools",
        "cons": "No extreme specialty, elite velocity or command arrives later",
        "detail": "Growth is distributed evenly between Velocity, Control, and Stamina. A safe path that avoids major holes in your game but lacks an immediate 'killer' tool.",
    },

    # Catchers
    "Iron Wall": {
        "desc": "An impenetrable defender who controls the run game.",
        "pros": "+Fielding (Blocking), +Throwing (Arm Strength), pitchers trust you",
        "cons": "-Speed is non-existent, offensive stats grow very slowly",
        "detail": "Fielding and Throwing attributes skyrocket, minimizing passed balls and stolen bases. Contact and Power gains are significantly muted.",
    },
    "Battery Bomber": {
        "desc": "A heavy hitter who brings run support from behind the dish.",
        "pros": "+Power, +Contact, creates a fearsome heart of the order",
        "cons": "-Fielding lags, slower pop-time on throws to second",
        "detail": "Power and Contact scale like a corner infielder. However, your Defense and Throwing take longer to develop, potentially hurting your pitcher's confidence.",
    },
    "Field General": {
        "desc": "A cerebral leader who elevates the entire pitching staff.",
        "pros": "+Mental, +Command bonus for pitchers (Framing), high Baseball IQ",
        "cons": "-Raw physical tools (Speed/Power) are average at best",
        "detail": "Mental attributes and technical Fielding (Framing) grow fast. While not a physical specimen, your presence stabilizes the battery's performance.",
    },
    "Balanced Catcher": {
        "desc": "A reliable backstop who contributes on both sides of the ball.",
        "pros": "Steady glove, respectable bat, versatile lineup usage",
        "cons": "Master of none; won't win Gold Gloves or Silver Sluggers early",
        "detail": "Splits experience evenly between defensive drills and batting practice. Good for a catcher who needs to play every day without being a liability anywhere.",
    },

    # Infielders
    "Glove Wizard": {
        "desc": "Defensive specialist who turns hits into outs.",
        "pros": "+Fielding range, +Throwing accuracy, quicker double plays",
        "cons": "-Power ceiling is low, relies on singles and walks",
        "detail": "Fielding and Reaction grow rapidly, making you elite at SS or 2B. Power is the tradeoff, limiting you to the bottom of the batting order early on.",
    },
    "Corner Crusher": {
        "desc": "A power source designed for the hot corner or first base.",
        "pros": "+Power, +Throwing (Arm Strength), intimidates opposing pitchers",
        "cons": "-Speed, -Fielding range, high strikeout risk",
        "detail": "Power and Throwing strength see major gains. Speed and lateral Fielding range are poor, making this style best suited for 1B or 3B.",
    },
    "Table Setter": {
        "desc": "Chaos agent who gets on base and makes things happen.",
        "pros": "+Speed, +Contact, excels at bunting and stealing",
        "cons": "-Power is minimal, weaker Throwing arm",
        "detail": "Speed and Contact are the priority, perfect for leadoff hitters. You won't hit many home runs, and your Throwing arm may limit you to 2B.",
    },
    "Balanced Infielder": {
        "desc": "A dependable glove and bat who fits any infield slot.",
        "pros": "Adaptable to 2B/SS/3B, steady development in all tools",
        "cons": "Lacks the elite range of a Wizard or the pop of a Crusher",
        "detail": "Even distribution of XP across Fielding, Contact, and Power. A safe bet for a utility player or a solid everyday starter with no major flaws.",
    },

    # Outfielders
    "Range Rover": {
        "desc": "A center-field prototype who covers gap to gap.",
        "pros": "+Speed, +Fielding range, tracks down difficult fly balls",
        "cons": "-Throwing power is average, -Power hitting is secondary",
        "detail": "Speed and Fielding receive the highest multipliers, essential for CF. Batting power is sacrificed for elite defensive coverage.",
    },
    "Laser Show": {
        "desc": "Right-field profile with an arm that stops runners.",
        "pros": "+Throwing (Arm Strength), +Power, punishes greedy baserunners",
        "cons": "-Speed is average, -Contact consistency",
        "detail": "Throwing and Power are the focus. You can gun down runners from the warning track, but you might strike out more often than contact hitters.",
    },
    "Gap Hunter": {
        "desc": "Offensive specialist who lives for extra-base hits.",
        "pros": "+Contact, +Power (Gap), high doubles/triples potential",
        "cons": "-Fielding instincts are slow, -Throwing accuracy",
        "detail": "Contact and Power grow efficiently. You are a bat-first outfielder (likely LF) where defensive shortcomings are easier to hide.",
    },
    "Balanced Outfielder": {
        "desc": "A five-tool hopeful who stays consistent.",
        "pros": "Good blend of Speed, Arm, and Bat; fits any OF spot",
        "cons": "Takes years to become elite in any single category",
        "detail": "Allocates training evenly across Speed, Fielding, and Batting. The ideal choice if you aren't sure which outfield position you will ultimately lock down.",
    },
}


def _load_growth_styles() -> Dict[str, Dict[str, str]]:
    """Load growth styles from JSON, falling back to the baked-in defaults on error."""

    data_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "growth_styles.json")
    )
    try:
        with open(data_path, "r", encoding="utf-8") as handle:
            parsed = json.load(handle)
        if not isinstance(parsed, dict):
            LOGGER.warning("growth_styles.json must be a JSON object; using defaults instead.")
            return dict(_DEFAULT_GROWTH_STYLE_INFO)
        return parsed
    except FileNotFoundError:
        LOGGER.warning("growth_styles.json not found; using defaults instead.")
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("growth_styles.json failed to load (%s); using defaults instead.", exc)
    return dict(_DEFAULT_GROWTH_STYLE_INFO)


GROWTH_STYLE_INFO = _load_growth_styles()

STEP_TITLES = {
    0: "Name Entry",
    1: "Select Position",
    2: "Roll Base Attributes",
    3: "Choose Growth Style",
    4: "Pick Hometown",
    5: "Select School",
    6: "Configure Pitch Arsenal",
    7: "Traits Gacha",
    8: "Confirm Profile",
}
TOTAL_STEPS = max(STEP_TITLES.keys()) + 1

PITCH_SELECTION_POOL = [
    "4-Seam Fastball",
    "2-Seam Fastball",
    "Cutter",
    "Power Cutter",
    "Sinker",
    "Turbo Sinker",
    "Shuuto",
    "Slider",
    "Sweeper",
    "Curveball",
    "Power Curve",
    "Knuckle Curve",
    "Changeup",
    "Circle Change",
    "Vulcan Change",
    "Splitter",
    "Forkball",
    "Split-Change",
]
PITCH_SELECTION_POOL = [pitch for pitch in PITCH_SELECTION_POOL if pitch in PITCH_TYPES]
DEFAULT_PITCH_ARSENAL = [pitch for pitch in ("4-Seam Fastball", "Slider", "Changeup") if pitch in PITCH_SELECTION_POOL][:3]
FASTBALL_PITCHES = {"4-Seam Fastball", "2-Seam Fastball", "Sinker", "Turbo Sinker", "Shuuto", "Cutter", "Power Cutter"}
MIN_PITCHES = 1
MAX_PITCHES = 4

_FASTBALLS = {"4-Seam Fastball", "2-Seam Fastball", "Cutter", "Power Cutter", "Sinker", "Turbo Sinker", "Shuuto"}
_BREAKERS = {"Slider", "Sweeper", "Curveball", "Power Curve", "Knuckle Curve"}
_CHANGEUPS = {"Changeup", "Circle Change", "Vulcan Change", "Split-Change"}


def _pitch_recommendations(selected: List[str], arm_slot: str | None) -> List[str]:
    """Lightweight pitch mix suggestions to guide new players."""
    picks = set(p.lower() for p in selected)
    recs: List[str] = []

    def _add(name: str, reason: str) -> None:
        if name.lower() in picks:
            return
        recs.append(f"{name} — {reason}")

    # Anchor: always suggest a true heater if missing.
    if not (_FASTBALLS & picks):
        _add("4-Seam Fastball", "Anchor velo pitch; everything else tunnels off it.")

    # Horizontal breaker.
    if not (_BREAKERS & picks):
        _add("Slider", "Glove-side breaker to pair with the heater.")

    # Off-speed / change of pace.
    if not (_CHANGEUPS & picks):
        _add("Circle Change", "Speed differential to disrupt timing.")

    # Vertical shape.
    has_vert = any(p in {"Curveball", "Power Curve", "Knuckle Curve"} for p in selected)
    if not has_vert:
        _add("Curveball", "Downward break to change eye level.")

    # Platoon/weak-contact tool if still under max.
    if len(recs) < 3:
        slot = (arm_slot or "").lower()
        if "side" in slot or "sub" in slot:
            _add("Sweeper", "Plays up from a lower slot with big sweep.")
        else:
            _add("Sinker", "Arm-side run for grounders and quick outs.")

    return recs[:4]


def _dedupe_preserve_order(items: Optional[List[str]]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items or []:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _seed_break_multiplier(pitch_name: str, arm_slot: str, axis: str) -> float:
    """Seed slight pitch-specific shape variance based on arm slot and randomness."""
    name = (pitch_name or "").lower()
    slot = (arm_slot or "three-quarters").lower()
    base = 1.0
    if axis == "h":
        if "sidearm" in slot or "sub" in slot:
            base += 0.1
        if "sinker" in name or "shuuto" in name:
            base += 0.08
        if "cutter" in name:
            base += 0.05
    else:
        if "overhand" in slot or "high three" in slot:
            base += 0.08
        if "curve" in name or "12-6" in name:
            base += 0.06
        if "split" in name or "fork" in name:
            base += 0.04
    jitter = random.uniform(-0.06, 0.08)
    return round(max(0.85, min(1.25, base + jitter)), 3)

_PREFECTURE_CACHE: Optional[List[str]] = None
_CITY_CACHE: Dict[str, List[Dict[str, Any]]] = {}

# Tokyo split handling: east = 23 wards; west = Tama area + islands.
TOKYO_EAST_CITIES = {
    "Adachi", "Arakawa", "Bunkyo", "Chiyoda", "Chuo", "Edogawa", "Itabashi",
    "Katsushika", "Kita", "Koto", "Meguro", "Minato", "Nakano", "Nerima",
    "Ota", "Setagaya", "Shibuya", "Shinagawa", "Shinjuku", "Suginami",
    "Sumida", "Taito", "Toshima",
}
TOKYO_WEST_CITIES = {
    "Hachioji", "Tachikawa", "Musashino", "Mitaka", "Ome", "Fuchu", "Akishima",
    "Chofu", "Machida", "Kodaira", "Hino", "Higashimurayama", "Kokubunji",
    "Koganei", "Fussa", "Komae", "Higashiyamato", "Kiyose", "Higashikurume",
    "Musashimurayama", "Inagi", "Hamura", "Akiruno", "Nishitokyo", "Mizuho",
    "Hinode", "Hinohara", "Okutama", "Ogasawara", "Hachijo", "Hachijo Jima",
    "Aogashima",
}


def _normalize_city_key(name: str) -> str:
    return "".join(ch.lower() for ch in (name or "") if ch.isalnum())


TOKYO_EAST_KEYS = {_normalize_city_key(c) for c in TOKYO_EAST_CITIES}
TOKYO_WEST_KEYS = {_normalize_city_key(c) for c in TOKYO_WEST_CITIES}


def _tokyo_side_for_city(city_name: str) -> str:
    key = _normalize_city_key(city_name)
    if key in TOKYO_EAST_KEYS:
        return "east"
    if key in TOKYO_WEST_KEYS:
        return "west"
    return "either"


def _filter_tokyo_cities(cities: List[Dict[str, Any]], side: Optional[str]) -> List[Dict[str, Any]]:
    if not side:
        return cities
    side = side.lower()
    filtered = []
    for entry in cities:
        city_name = entry.get("name") or ""
        bucket = _tokyo_side_for_city(city_name)
        if bucket == "either" or bucket == side:
            filtered.append(entry)
    return filtered


def _io_log(io: Optional[IOInterface], message: str, *, level: str = "info") -> None:
    if io:
        io.log(message, level=level)
    else:
        print(message)


def _io_prompt(io: Optional[IOInterface], prompt: str, *, options: Optional[List[str]] = None, default: str = "") -> str:
    if io:
        return io.prompt(prompt, options=options)
    try:
        response = input(prompt)
    except (EOFError, KeyboardInterrupt):
        return default
    if options and response not in options:
        return default
    return response if response else default


def _validate_name(first: str, last: str) -> Tuple[bool, str]:
    if not first:
        return False, "First name is required."
    if not last:
        return False, "Last name is required."
    return True, ""


def _reset_hometown_cache() -> None:
    global _PREFECTURE_CACHE, _CITY_CACHE
    _PREFECTURE_CACHE = None
    _CITY_CACHE = {}


def get_prefecture_catalog(session: Session) -> List[str]:
    global _PREFECTURE_CACHE
    if _PREFECTURE_CACHE is not None:
        return _PREFECTURE_CACHE
    if session is None:
        return []

    try:
        rows = (
            session.query(School.prefecture)
            .group_by(School.prefecture)
            .order_by(School.prefecture)
            .all()
        )
        _PREFECTURE_CACHE = [row[0] for row in rows if row[0]]
    except SQLAlchemyError as exc:
        LOGGER.warning("Prefecture lookup failed: %s", exc)
        _PREFECTURE_CACHE = []
    return _PREFECTURE_CACHE


def _load_cities_for_prefecture(session: Session, prefecture: str) -> List[Dict[str, Any]]:
    cached = _CITY_CACHE.get(prefecture)
    if cached is not None:
        return cached
    if session is None:
        _CITY_CACHE[prefecture] = []
        return _CITY_CACHE[prefecture]

    try:
        rows = (
            session.query(
                School.city_name,
                func.count(School.id).label("schools"),
            )
            .filter(School.prefecture == prefecture)
            .filter(School.city_name.isnot(None))
            .group_by(School.city_name)
            .order_by(func.count(School.id).desc(), func.lower(School.city_name))
            .all()
        )
        city_rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows, start=1):
            city_name = row[0]
            if not city_name:
                continue
            city_rows.append({
                "name": city_name,
                "school_count": row[1],
                "ordinal": idx,
            })
    except SQLAlchemyError as exc:
        LOGGER.warning("City lookup failed for %s: %s", prefecture, exc)
        city_rows = []

    _CITY_CACHE[prefecture] = city_rows
    return city_rows

def _render_city_directory(prefecture: str, cities: List[Dict[str, Any]], columns: int = 3) -> None:
    # UI-specific rendering handled by the view layer; retain for compatibility when IO is absent.
    if not cities:
        print(f"No registered baseball schools for {prefecture} yet.")
        return

    col_width = 84 // max(columns, 1)
    for idx, entry in enumerate(cities, start=1):
        label = f"{entry['name']} ({entry['school_count']})"
        print(label.ljust(col_width), end="")
        if idx % columns == 0:
            print()
    if len(cities) % columns != 0:
        print()
    print(f"Cities with active programs: {len(cities)}")


def _prefecture_grid(prefectures: List[str], cols: int = 3, col_width: int = 24, *, highlight: Optional[int] = None) -> List[str]:
    lines: List[str] = []
    border = "+" + "+".join(["-" * col_width] * cols) + "+"
    lines.append(border)
    for i in range(0, len(prefectures), cols):
        cells = []
        for j in range(cols):
            idx = i + j
            if idx < len(prefectures):
                pointer = ">" if highlight == idx else " "
                label = f" {pointer} {prefectures[idx]}"
            else:
                label = ""
            cells.append(label.ljust(col_width))
        lines.append("|" + "|".join(cells) + "|")
        lines.append(border)
    return lines


def _city_grid(cities: List[Dict[str, Any]], cols: int = 2, col_width: int = 30, *, highlight: Optional[int] = None) -> List[str]:
    lines: List[str] = []
    border = "+" + "+".join(["-" * col_width] * cols) + "+"
    lines.append(border)
    for i in range(0, len(cities), cols):
        cells = []
        for j in range(cols):
            idx = i + j
            if idx < len(cities):
                name = cities[idx].get("name", "--")
                count = cities[idx].get("school_count", "")
                pointer = ">" if highlight == idx else " "
                label = f" {pointer} {name} ({count})" if count else f" {pointer} {name}"
            else:
                label = ""
            cells.append(label.ljust(col_width))
        lines.append("|" + "|".join(cells) + "|")
        lines.append(border)
    return lines


def _options_grid(
    options: List[str],
    cols: int = 2,
    col_width: int = 32,
    *,
    start_index: int = 1,
    highlight: Optional[int] = None,
) -> List[str]:
    lines: List[str] = []
    border = "+" + "+".join(["-" * col_width] * cols) + "+"
    lines.append(border)
    for i in range(0, len(options), cols):
        cells = []
        for j in range(cols):
            idx = i + j
            if idx < len(options):
                pointer = ">" if highlight == idx else " "
                label = f" {pointer} {options[idx]}"
            else:
                label = ""
            cells.append(label.ljust(col_width))
        lines.append("|" + "|".join(cells) + "|")
        lines.append(border)
    return lines


def _pitch_grid(
    pitches: List[str],
    selected: List[str],
    cols: int = 2,
    col_width: int = 36,
    highlight: Optional[int] = None,
) -> List[str]:
    selected_set = {p.lower() for p in selected}
    lines: List[str] = []
    border = "+" + "+".join(["-" * col_width] * cols) + "+"
    lines.append(border)
    for i in range(0, len(pitches), cols):
        cells = []
        for j in range(cols):
            idx = i + j
            if idx < len(pitches):
                name = pitches[idx]
                mark = "[x]" if name.lower() in selected_set else "[ ]"
                pointer = ">" if highlight == idx else " "
                label = f"{pointer} {mark} {name}"
            else:
                label = ""
            cells.append(label.ljust(col_width))
        lines.append("|" + "|".join(cells) + "|")
        lines.append(border)
    return lines


def _growth_detail_lines(style: str) -> List[str]:
    info = GROWTH_STYLE_INFO.get(style, {})
    desc = info.get("desc") or "No description available."
    pros = info.get("pros") or "--"
    cons = info.get("cons") or "--"
    detail = info.get("detail") or ""
    lines = [f"{style} Overview:", f"Summary: {desc}", f"Upside: {pros}", f"Tradeoffs: {cons}"]
    if detail:
        lines.extend(["", detail])
    return lines


def get_city_matches(session: Session, prefecture: str, search_term: str = "") -> List[Dict[str, Any]]:
    cities = _load_cities_for_prefecture(session, prefecture)
    if not cities:
        return []

    term = search_term.strip().lower()
    filtered = [c for c in cities if term in c['name'].lower()] if term else cities
    return filtered[:20]


def _bar(value: Optional[int], width: int = 20) -> str:
    if value is None:
        return " " * width
    pct = max(0, min(99, int(value))) / 100
    filled = int(pct * width)
    return ("█" * filled) + ("░" * (width - filled))


def _stat_lines(position: str, stats: dict) -> List[str]:
    """Render a quick ASCII stat block for the current roll."""
    lines: List[str] = []
    if not stats:
        return lines

    is_pitcher = position == "Pitcher"

    general_fields = [
        ("Contact", stats.get("contact")),
        ("Power", stats.get("power")),
        ("Speed", stats.get("speed")),
        ("Fielding", stats.get("fielding")),
        ("Throwing", stats.get("throwing")),
    ]
    if not is_pitcher:
        general_fields.append(("Velocity", stats.get("velocity")))

    lines.append("-- GENERAL --")
    for label, value in general_fields:
        bar = _bar(value)
        val_txt = f"{int(value):>3}" if value is not None else "--"
        lines.append(f" {label:<10} {bar}  {val_txt}")

    if is_pitcher:
        lines.append("")
        lines.append("-- PITCHING --")
        pitch_fields = [
            ("Velocity", stats.get("velocity")),
            ("Control", stats.get("control")),
            ("Command", stats.get("command")),
            ("Movement", stats.get("movement")),
            ("Stamina", stats.get("stamina")),
        ]
        for label, value in pitch_fields:
            bar = _bar(value)
            val_txt = f"{int(value):>3}" if value is not None else "--"
            lines.append(f" {label:<10} {bar}  {val_txt}")
        if stats.get("arm_slot"):
            lines.append(f" Arm Slot   {stats['arm_slot']}")

    if position == "Catcher":
        wall = stats.get("catcher_ability")
        if wall is not None:
            bar = _bar(wall)
            val_txt = f"{int(wall):>3}" if wall is not None else "--"
            lines.append("")
            lines.append("-- CATCHER --")
            lines.append(f" Wall (CAA)  {bar}  {val_txt}")

    return lines


def _render_creation_banner(step: int, data: dict, subtitle: str) -> None:
    # Deprecated direct rendering retained for legacy CLI usage.
    lines = _banner_lines(step, data, subtitle, preview=None)
    for line in lines:
        print(line)


def _banner_lines(step: int, data: dict, subtitle: str, preview: Optional[List[str]] = None) -> List[str]:
    stage_index = min(step, TOTAL_STEPS - 1)
    stage = stage_index + 1
    border = "═" * 84
    title = f"CHARACTER CREATION  |  STEP {stage}/{TOTAL_STEPS}"

    full_name = " ".join(part for part in [data.get('last_name'), data.get('first_name')] if part).strip()
    focus = data.get('specific_pos') or '--'
    pos = data.get('position') or '--'
    hometown = data.get('hometown') or '--'
    school_obj = data.get('school')
    school_name = getattr(school_obj, 'name', None) if school_obj else None

    summary = [
        f"Name: {full_name or '--'}",
        f"Focus: {focus} ({pos})",
        f"Hometown: {hometown}",
        f"School: {school_name or '--'}",
    ]

    lines = [
        border,
        title.center(84),
        subtitle.center(84),
        border,
        *[line.ljust(84) for line in summary],
    ]
    if preview:
        lines.extend(line.ljust(84) for line in preview)
    lines.append("─" * 84)
    return lines


def _preview_lines(state: "CreatePlayerState") -> List[str]:
    """Compact player preview always shown at the top of the flow."""

    lines: List[str] = []
    name = f"{state.last_name} {state.first_name}".strip() or "--"
    role = state.specific_pos or state.position or "--"
    growth = state.growth_style or "--"
    hometown = state.hometown or "--"
    school = getattr(state.school, "name", "--") if state.school else "--"

    lines.append(f"PREVIEW :: {name} | {role} | {growth}")
    lines.append(f"Home: {hometown} | School: {school}")

    stats = state.stats or {}
    if stats:
        if state.position == "Pitcher":
            core = [
                f"V{stats.get('velocity','--')}",
                f"C{stats.get('control','--')}",
                f"M{stats.get('movement','--')}",
                f"St{stats.get('stamina','--')}",
            ]
            slot = stats.get("arm_slot")
            if slot:
                core.append(slot)
        else:
            core = [
                f"Con{stats.get('contact','--')}",
                f"Pow{stats.get('power','--')}",
                f"Spd{stats.get('speed','--')}",
                f"Fld{stats.get('fielding','--')}",
                f"Arm{stats.get('throwing','--')}",
                f"Velo{stats.get('velocity','--')}",
            ]
            if state.position == "Catcher":
                core.append(f"Wall{stats.get('catcher_ability','--')}")
        lines.append("Stats: " + " | ".join(str(c) for c in core))

    if state.position == "Pitcher" and state.pitch_arsenal:
        lines.append("Pitches: " + ", ".join(_dedupe_preserve_order(state.pitch_arsenal)))
    lines.append("")  # spacer
    return lines


def _render_stat_overview(position: str, stats: dict) -> None:
    # Deprecated direct rendering retained for legacy CLI usage.
    if not stats:
        return
    if position == "Pitcher":
        fields = [
            ("Velocity", stats.get('velocity')),
            ("Control", stats.get('control')),
            ("Movement", stats.get('movement')),
            ("Stamina", stats.get('stamina')),
        ]
    else:
        fields = [
            ("Contact", stats.get('contact')),
            ("Power", stats.get('power')),
            ("Speed", stats.get('speed')),
            ("Fielding", stats.get('fielding')),
            ("Throwing", stats.get('throwing')),
            ("Velocity", stats.get('velocity')),
        ]
        if position == "Catcher":
            fields.append(("Catcher Ability", stats.get('catcher_ability')))
    for label, value in fields:
        bar = _bar(value)
        val_txt = f"{int(value):>3}" if value is not None else "--"
        print(f" {label:<10} {bar}  {val_txt}")
    if position == "Pitcher" and stats.get('arm_slot'):
        print(f" Arm Slot   {stats['arm_slot']}")


def _print_option(title: str) -> None:
    # Deprecated direct rendering retained for legacy CLI usage.
    print(title)


def _validate_pitch_selection(selection: Optional[List[str]]) -> Tuple[bool, str]:
    picks = [p for p in _dedupe_preserve_order(selection) if p in PITCH_SELECTION_POOL]
    if len(picks) < MIN_PITCHES:
        return False, f"Select at least {MIN_PITCHES} pitches."
    if len(picks) > MAX_PITCHES:
        return False, f"You can only bring {MAX_PITCHES} pitches."
    return True, ""


# ------------------------------------------------------
#  ROLL STATS  — now includes HEIGHT SYSTEM (A + B)
# ------------------------------------------------------
def roll_stats(position, is_monster=False):
    stats = {}
    base_min = 30; base_max = 50
    if is_monster: 
        base_min = 65; base_max = 85

    def get_val(bonus=0):
        return max(10, min(99, random.randint(base_min + bonus, base_max + bonus)))

    def _derived_velocity(throwing: int, base: float, scale: float) -> int:
        """Map throwing to a velocity-ish scale (kph) with sane bounds."""
        return max(70, min(155, int(base + (throwing or 0) * scale)))

    # Growth Tag
    roll = random.random()
    if roll < 0.01: stats['growth_tag'] = "Limitless"
    elif roll < 0.15: stats['growth_tag'] = "Sleeping Giant"
    elif roll < 0.35: stats['growth_tag'] = "Supernova"
    elif roll < 0.50: stats['growth_tag'] = "Grinder"
    else: stats['growth_tag'] = "Normal"

    # Potential Grade
    pot_roll = random.random()
    if stats['growth_tag'] == "Limitless": stats['potential_grade'] = "S"
    elif pot_roll < 0.10: stats['potential_grade'] = "S"
    elif pot_roll < 0.30: stats['potential_grade'] = "A"
    elif pot_roll < 0.60: stats['potential_grade'] = "B"
    else: stats['potential_grade'] = "C"

    # ---------------------------
    #  HEIGHT SYSTEM (NEW)
    # ---------------------------
    base_h = 175
    base_w = 72
    if position == "Pitcher":
        base_h = 178; base_w = 75
    elif position in ["1B", "3B"]:
        base_h = 180; base_w = 80

    # starting height/weight
    stats['height_cm'] = int(random.normalvariate(base_h, 5))
    stats['weight_kg'] = int(random.normalvariate(base_w, 8))

    # height potential (5–20 cm above start)
    stats['height_potential'] = stats['height_cm'] + random.randint(5, 20)

    # how many years they still grow (1–3)
    stats['height_growth_years'] = random.choice([1, 2, 3])

    # Two-way profile (rare)
    is_two_way, secondary = roll_two_way_profile(position, rng=random)
    stats['is_two_way'] = is_two_way
    stats['secondary_position'] = secondary if secondary else None

    # Soft-tune secondary skill penalties so two-way players keep their playable tools.
    weak_stat_mod = 5 if is_two_way else -5
    very_weak_stat_mod = 5 if is_two_way else 0
    throwing_bonus = 10 if is_two_way else 5

    # ---------------------------
    #  Player Skill Stats
    # ---------------------------
    # Core attributes tuned per position
    if position == "Pitcher":
        stats['velocity'] = random.randint(130, 152) + (10 if is_monster else 0)
        stats['control'] = get_val(10)
        stats['command'] = get_val(8)
        stats['movement'] = get_val(10)
        stats['stamina'] = get_val(10)
        stats['power'] = get_val(weak_stat_mod)
        stats['contact'] = get_val(weak_stat_mod)
        stats['speed'] = get_val(weak_stat_mod)
        stats['fielding'] = get_val(very_weak_stat_mod)
        stats['throwing'] = get_val(throwing_bonus)
        stats['arm_slot'] = roll_arm_slot("pitching")
    elif position == "Catcher":
        stats['stamina'] = get_val(5)
        stats['control'] = get_val(-5)
        stats['movement'] = get_val(-5)
        stats['power'] = get_val(-5)
        stats['contact'] = get_val(5)
        stats['speed'] = get_val(-10)
        stats['fielding'] = get_val(10)
        stats['throwing'] = get_val(15)
        stats['velocity'] = _derived_velocity(stats['throwing'], 85, 0.60)
        stats['arm_slot'] = "Three-Quarters"
        stats['catcher_leadership'] = max(20, min(95, int((stats['fielding'] + stats['control'] + stats['discipline']) / 3)))
    elif position in {"First Base", "Third Base"}:
        stats['stamina'] = get_val()
        stats['control'] = get_val(-10)
        stats['movement'] = get_val(-10)
        stats['power'] = get_val(15)
        stats['contact'] = get_val(5)
        stats['speed'] = get_val(-10)
        stats['fielding'] = get_val()
        stats['throwing'] = get_val()
        stats['velocity'] = _derived_velocity(stats['throwing'], 82, 0.55)
        stats['arm_slot'] = "Three-Quarters"
    elif position in {"Second Base", "Shortstop"}:
        stats['stamina'] = get_val()
        stats['control'] = get_val(-5)
        stats['movement'] = get_val(-5)
        stats['power'] = get_val(-5)
        stats['contact'] = get_val(5)
        stats['speed'] = get_val(10)
        stats['fielding'] = get_val(15)
        stats['throwing'] = get_val(5)
        stats['velocity'] = _derived_velocity(stats['throwing'], 84, 0.60)
        stats['arm_slot'] = "Three-Quarters"
    else:  # Outfield
        stats['power'] = get_val(10)
        stats['contact'] = get_val()
        stats['speed'] = get_val(15)
        stats['fielding'] = get_val(5)
        stats['throwing'] = get_val(10)
        velo_mult = 0.75 if is_two_way else 0.65
        stats['velocity'] = int(90 + (stats['throwing'] * velo_mult))
        stats['control'] = get_val(weak_stat_mod)
        stats['movement'] = get_val(-5)
        stats['stamina'] = get_val(weak_stat_mod + 5)
        stats['arm_slot'] = "Three-Quarters"

    # Wall (catcher ability): reflexes + focus. Catchers get a derived value; others default to 0.
    if position == "Catcher":
        base_wall = (stats['fielding'] + random.randint(40, 70)) // 2
        stats['catcher_ability'] = max(10, min(99, base_wall))
    else:
        stats['catcher_ability'] = 0

    return stats


# ------------------------------------------------------
# SAVE PLAYER TO DB (now includes height fields)
# ------------------------------------------------------
def commit_player_to_db(session: Session, data) -> int:
    s = data['stats']
    # Do not auto-assign default pitches; player must pick 1-4 in the menu.
    valid_cols = [c.key for c in Player.__table__.columns]
    clean_stats = {k: v for k, v in s.items() if k in valid_cols}

    # Ensure arm slot persists even if upstream stats dict was missing it
    if 'arm_slot' in valid_cols and 'arm_slot' not in clean_stats:
        clean_stats['arm_slot'] = s.get('arm_slot') or "Three-Quarters"

    if 'academic_skill' not in clean_stats or 'test_score' not in clean_stats:
        academic_skill, test_score = roll_academic_profile(data.get('hometown'), data.get('school'))
        clean_stats['academic_skill'] = academic_skill
        clean_stats['test_score'] = test_score

    if data.get('starter_trait') and data.get('position') == "Pitcher":
        clean_stats['is_starter'] = True
        clean_stats['role'] = "STARTER"
    else:
        clean_stats.setdefault('is_starter', False)

    # Ensure Wall stat exists for catchers even if upstream rolling missed it
    if data.get('position') == "Catcher":
        clean_stats['catcher_ability'] = clean_stats.get('catcher_ability', 0) or max(10, int((clean_stats.get('fielding', 50) + 50) / 2))
        clean_stats['catcher_leadership'] = clean_stats.get('catcher_leadership', 0) or max(
            20,
            int((clean_stats.get('discipline', 50) + clean_stats.get('fielding', 50)) / 2),
        )
    else:
        clean_stats.setdefault('catcher_ability', 0)
        clean_stats.setdefault('catcher_leadership', 0)

    # Seed a base mechanics blob for pitchers so pitch lab and gameplay have data.
    if data.get('position') == "Pitcher":
        clean_stats.setdefault('mechanics_json', "{}")

    # Compute a quick overall rating (0-99) based on primary tools.
    def _avg(pool):
        values = [v for v in pool if isinstance(v, (int, float))]
        return sum(values) / len(values) if values else 0

    if data.get('position') == "Pitcher":
        overall = int(_avg([
            clean_stats.get('velocity', 0),
            clean_stats.get('control', 0),
            clean_stats.get('command', clean_stats.get('control', 0)),
            clean_stats.get('movement', 0),
            clean_stats.get('stamina', 0),
        ]))
    else:
        overall = int(_avg([
            clean_stats.get('contact', 0),
            clean_stats.get('power', 0),
            clean_stats.get('speed', 0),
            clean_stats.get('fielding', 0),
            clean_stats.get('throwing', 0),
        ]))
    clean_stats['overall'] = max(0, min(99, overall))

    growth_tag = clean_stats.pop("growth_tag", None)
    growth_style = data.get("growth_style") or clean_stats.pop("growth_style", None)
    traits = roll_player_personality(data.get('school'))
    clean_stats.setdefault('drive', traits['drive'])
    clean_stats.setdefault('loyalty', traits['loyalty'])
    clean_stats.setdefault('volatility', traits['volatility'])
    determination_seed = traits['drive'] + random.randint(-6, 6)
    clean_stats.setdefault('determination', max(30, min(95, determination_seed)))
    clean_stats.setdefault('ability_points', 0)

    p = Player(
        first_name=data['first_name'],
        last_name=data['last_name'],
        name=f"{data['last_name']} {data['first_name']}",
        position=data['position'],
        year=1,
        school_id=data['school'].id,
        jersey_number=1 if data['position'] == "Pitcher" else 5,
        fatigue=0,
        injury_days=0,
        trust_baseline=50,

        growth_tag=growth_tag,
        growth_style=growth_style,

        **clean_stats
    )

    session.add(p)
    session.commit()
    session.refresh(p)

    _persist_pitch_arsenal(session, p, data.get('pitch_arsenal'), clean_stats)
    seed_relationships(session, p)
    grant_user_creation_trait_rolls(session, p, rolls=3)
    maybe_assign_bad_trait(session, p)
    assign_theme_if_eligible(p)
    return p.id


def _persist_pitch_arsenal(session: Session, player: Player, pitch_names: Optional[List[str]], stats: dict) -> None:
    if not player or player.position != "Pitcher":
        return

    picks = _dedupe_preserve_order([p for p in (pitch_names or []) if p in PITCH_SELECTION_POOL])
    if not picks:
        picks = list(DEFAULT_PITCH_ARSENAL)

    # Clamp to allowed limits
    arsenal = picks[:MAX_PITCHES] if picks else list(DEFAULT_PITCH_ARSENAL)
    quality_seed = int((stats.get("control", 50) + stats.get("velocity", 50)) / 2)
    break_seed = int(stats.get("movement", 50) / 2)

    arm_slot = stats.get("arm_slot") or getattr(player, "arm_slot", "Three-Quarters")
    height_cm = getattr(player, "height_cm", stats.get("height_cm", 175))
    height_ft = max(5.0, min(7.5, height_cm / 30.48))
    base_release = 5.5 if "Sidearm" in arm_slot or "Submarine" in arm_slot else 6.2
    base_extension = 6.0 + max(0.0, (height_ft - 6.0) * 0.6)

    for name in arsenal:
        repertoire_row = PitchRepertoire(
            player_id=getattr(player, "id", None),
            pitch_name=name,
            quality=max(30, min(95, quality_seed)),
            break_level=max(0, min(90, break_seed)),
            mastery_xp=0,
            mastery_level=0,
            signature_ready=False,
            signature_unlocked=False,
            h_break_mult=_seed_break_multiplier(name, arm_slot, axis="h"),
            v_break_mult=_seed_break_multiplier(name, arm_slot, axis="v"),
            release_height=base_release + random.uniform(-0.3, 0.3),
            extension=base_extension + random.uniform(-0.4, 0.4),
        )
        session.add(repertoire_row)
    session.flush()

# ------------------------------------------------------
# DECISION-BASED CHARACTER CREATION ENGINE
# ------------------------------------------------------
from dataclasses import dataclass, field

from core.decisions import DecisionRequest, DecisionResult


@dataclass
class CreatePlayerState:
    first_name: str = ""
    last_name: str = ""
    position: Optional[str] = None
    specific_pos: Optional[str] = None
    growth_style: Optional[str] = None
    stats: Optional[dict] = None
    rerolls_left: int = 3
    hometown: Optional[str] = None
    prefecture_choice: Optional[str] = None
    school: Optional[School] = None
    pitch_arsenal: List[str] = field(default_factory=list)
    starter_trait: Optional[bool] = None


class CreatePlayerEngine:
    """State machine that emits DecisionRequests instead of blocking IO."""

    def __init__(self, session: Session):
        self.session = session
        self.state = CreatePlayerState()
        self.step = 0
        self._awaiting: Optional[str] = None
        self._scratch: dict = {}

    # --------- helpers ---------
    def _prompt(self, message: str, *, options: Optional[List[str]] = None, default: str = "") -> DecisionResult:
        request = DecisionRequest(kind="prompt", message=message, options=options, default=default)
        return DecisionResult(summary=None, requests=[request], done=False, data=self._serialize_state())

    def _log_and_prompt(self, lines: List[str], prompt: DecisionRequest) -> DecisionResult:
        # Clear screen first to avoid clutter, then emit lines and prompt.
        requests = [DecisionRequest(kind="log", message=CLEAR_SCREEN)]
        requests.extend(DecisionRequest(kind="log", message=line) for line in lines)
        requests.append(prompt)
        return DecisionResult(summary=None, requests=requests, done=False, data=self._serialize_state())

    def _with_banner(self, subtitle: str, body: List[str]) -> List[str]:
        preview = _preview_lines(self.state)
        header = _banner_lines(self.step, self.state.__dict__, subtitle, preview=preview)
        return header + body

    def _serialize_state(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "state": self.state.__dict__,
        }

    # --------- step processing ---------
    def advance(self, response: Optional[str] = None) -> DecisionResult:
        # Handle response to previous prompt
        if self._awaiting:
            # Map ESC token to the common back value "0" so handlers do not need to change.
            if response == "__ESC__":
                response = "0"
            handler = getattr(self, f"_handle_{self._awaiting}")
            handler(response or "")
            self._awaiting = None

        if self.is_complete():
            return DecisionResult(
                summary="Character created",
                requests=[],
                done=True,
                data={"player_id": self.result()},
            )

        while True:
            if self.step == 0:
                return self._step_name_entry()
            if self.step == 1:
                return self._step_position()
            if self.step == 2:
                return self._step_stats()
            if self.step == 3:
                return self._step_growth_style()
            if self.step == 4:
                return self._step_hometown()
            if self.step == 5:
                return self._step_school()
            if self.step == 6:
                return self._step_pitch_arsenal()
            if self.step == 7:
                return self._step_trait_roll()
            if self.step == 8:
                return self._step_finalize()
            return DecisionResult(summary="Invalid step", requests=[], done=True, data=self._serialize_state())

    # --- Step 0: name ---
    def _step_name_entry(self) -> DecisionResult:
        if "name_phase" not in self._scratch:
            self._scratch["name_phase"] = "first"
        phase = self._scratch["name_phase"]

        if phase == "first":
            self._awaiting = "name_first"
            err = self._scratch.pop("name_error", None)
            body = ["Enter first name to populate the preview."]
            if err:
                body.append(f"Error: {err}")
            lines = self._with_banner(STEP_TITLES.get(0, "Name Entry"), body)
            return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="First Name: "))
        if phase == "last":
            self._awaiting = "name_last"
            body = ["Enter last name to complete the preview."]
            lines = self._with_banner(STEP_TITLES.get(0, "Name Entry"), body)
            return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="Last Name: "))
        if phase == "confirm":
            self._awaiting = "name_confirm"
            full = f"{self.state.last_name} {self.state.first_name}".strip()
            prefix = self._with_banner(
                STEP_TITLES.get(0, "Name Entry"), [f"Name: {full or '--'}", "Confirm this name?"]
            )
            suffix = ["Use arrows + Enter; Esc to go back."]
            requests = [DecisionRequest(kind="log", message=CLEAR_SCREEN)]
            requests.append(
                DecisionRequest(
                    kind="prompt",
                    message="",
                    options=["YES", "NO"],
                    default="1",
                    input_mode="binary_yes_no",
                    payload={"prefix": prefix, "suffix": suffix},
                )
            )
            return DecisionResult(summary=None, requests=requests, done=False, data=self._serialize_state())
        # done
        self._scratch.pop("name_phase", None)
        self.step += 1
        return self.advance()

    def _handle_name_first(self, value: str) -> None:
        if value.strip():
            self.state.first_name = value.strip()
        self._scratch["name_phase"] = "last"

    def _handle_name_last(self, value: str) -> None:
        if value.strip():
            self.state.last_name = value.strip()
        self._scratch["name_phase"] = "confirm"

    def _handle_name_confirm(self, value: str) -> None:
        valid, msg = _validate_name(self.state.first_name, self.state.last_name)
        if not valid:
            self._scratch["name_phase"] = "first"
            self._scratch["name_error"] = msg
            return
        if value in {"1", "yes", "YES"} or (value or "").lower().startswith("y"):
            self._scratch.pop("name_phase", None)
            self.step += 1
        else:
            self._scratch["name_phase"] = "first"

    # --- Step 1: position ---
    def _step_position(self) -> DecisionResult:
        phase = self._scratch.get("position_phase", "choose")
        candidate = self._scratch.get("position_candidate")
        positions = [
            "Pitcher",
            "Catcher",
            "First Base",
            "Second Base",
            "Third Base",
            "Shortstop",
            "Left Field",
            "Center Field",
            "Right Field",
        ]
        if phase == "confirm" and candidate:
            lines = [f"Confirm Position: {candidate}"]
            prefix = self._with_banner(STEP_TITLES.get(1, "Select Position"), lines)
            suffix = ["Use arrows + Enter to confirm or change."]
            self._awaiting = "position_confirm"
            return DecisionResult(
                summary=None,
                requests=[
                    DecisionRequest(kind="log", message=CLEAR_SCREEN),
                    DecisionRequest(
                        kind="prompt",
                        message="",
                        options=["Confirm", "Change"],
                        default="1",
                        input_mode="menu_grid",
                        payload={"prefix": prefix, "suffix": suffix, "cols": 2, "col_width": 22},
                    ),
                ],
                done=False,
                data=self._serialize_state(),
            )

        prefix = self._with_banner(
            STEP_TITLES.get(1, "Select Position"), ["Select Player Position (Esc to go back)"]
        )
        suffix = ["Use arrows + Enter to select. Esc disabled to prevent reroll hopping."]
        self._awaiting = "position_pick"
        requests = [DecisionRequest(kind="log", message=CLEAR_SCREEN)]
        requests.append(
            DecisionRequest(
                kind="prompt",
                message="",
                options=positions,
                default="1",
                input_mode="menu_grid",
                payload={
                    "prefix": prefix,
                    "suffix": suffix,
                    "cols": 3,
                    "col_width": 26,
                },
            )
        )
        return DecisionResult(summary=None, requests=requests, done=False, data=self._serialize_state())

    def _handle_position_pick(self, value: str) -> None:
        if value == "0":
            self.step = max(0, self.step - 1)
            return
        if not value.isdigit():
            return
        positions = [
            "Pitcher",
            "Catcher",
            "First Base",
            "Second Base",
            "Third Base",
            "Shortstop",
            "Left Field",
            "Center Field",
            "Right Field",
        ]
        pick = int(value) - 1
        if 0 <= pick < len(positions):
            specific = positions[pick]
            self._scratch["position_candidate"] = specific
            self._scratch["position_phase"] = "confirm"

    def _handle_position_confirm(self, value: str) -> None:
        if value == "2":
            self._scratch["position_phase"] = "choose"
            return
        if value not in {"1", "Confirm", "confirm"}:
            return
        specific = self._scratch.get("position_candidate")
        if not specific:
            self._scratch["position_phase"] = "choose"
            return
        self.state.specific_pos = specific
        if specific == "Pitcher":
            self.state.position = "Pitcher"
        elif specific == "Catcher":
            self.state.position = "Catcher"
        elif specific in {"First Base", "Second Base", "Third Base", "Shortstop"}:
            self.state.position = "Infielder"
        else:
            self.state.position = "Outfielder"
        if self.state.position != "Pitcher":
            self.state.pitch_arsenal = []
            self.state.starter_trait = None
        else:
            self.state.starter_trait = None
        self._scratch.pop("position_phase", None)
        self._scratch.pop("position_candidate", None)
        self.step += 1

    # --- Step 7: trait roll (moved near end) ---
    def _step_trait_roll(self) -> DecisionResult:
        if not self.state.position:
            self.step = 0
            return self.advance()
        if self.state.position != "Pitcher":
            self.state.starter_trait = None
            self.step += 1
            return self.advance()

        status = self.state.starter_trait
        if status is None:
            self._awaiting = "starter_roll"
            stats_block = _stat_lines(self.state.position or "", self.state.stats or {})
            header = self._with_banner(
                STEP_TITLES.get(7, "Traits Gacha"),
                [
                    "Traits Gacha",
                    "One pull decides if you walk away with the Starter tag.",
                    "Odds: 35% chance. No rerolls.",
                    "",
                    *stats_block,
                    "",
                ],
            )
            return DecisionResult(
                summary=None,
                requests=[
                    DecisionRequest(kind="log", message=CLEAR_SCREEN),
                    DecisionRequest(
                        kind="prompt",
                        message="",
                        options=["Spin"],
                        default="1",
                        input_mode="starter_spin",
                        payload={
                            "header": header,
                            "odds": 0.35,
                            "label": "Starter Trait",
                        },
                    ),
                ],
                done=False,
                data=self._serialize_state(),
            )

        lines = [
            "Starter Trait secured." if status else "No Starter Trait. Earn it through performance.",
            "",
        ]
        suffix = ["Use arrows + Enter to continue; Esc to go back."]
        self._awaiting = "starter_ack"
        prefix = self._with_banner(STEP_TITLES.get(7, "Traits Gacha"), lines)
        return DecisionResult(
            summary=None,
            requests=[
                DecisionRequest(kind="log", message=CLEAR_SCREEN),
                DecisionRequest(
                    kind="prompt",
                    message="",
                    options=["Continue"],
                    default="1",
                    input_mode="menu_grid",
                    payload={"prefix": prefix, "suffix": suffix, "cols": 1, "col_width": 32},
                ),
            ],
            done=False,
            data=self._serialize_state(),
        )

    def _handle_starter_roll(self, value: str) -> None:
        if value == "0":
            self.step = max(0, self.step - 1)
            return
        if value in {"WIN", "LOSE"}:
            self.state.starter_trait = value == "WIN"
        elif value == "1":
            self.state.starter_trait = random.random() < 0.35
        # stay on step to acknowledge result

    def _handle_starter_ack(self, value: str) -> None:
        if value == "0":
            self.state.starter_trait = None
            return
        if value == "1":
            self.step += 1

    # --- Step 3: stats / rerolls ---
    def _step_stats(self) -> DecisionResult:
        if self.state.stats is None:
            self.state.stats = roll_stats(self.state.position)
        s = self.state.stats
        lines = [
            f"Rerolls left: {self.state.rerolls_left}",
            f"HEIGHT: {s['height_cm']} cm",
            f"WEIGHT: {s['weight_kg']} kg",
        ]
        lines.extend(_stat_lines(self.state.position or "", s))
        if s.get('is_two_way') and s.get('secondary_position'):
            primary = self.state.position or 'Primary'
            lines.append(f"TWO-WAY POTENTIAL: {primary} / {s['secondary_position']}")
        options = [
            "Accept stats",
            "Reroll" + (" (LOCKED)" if self.state.rerolls_left <= 0 else ""),
        ]
        self._awaiting = "stats_choice"
        prefix = self._with_banner(STEP_TITLES.get(3, "Roll Base Attributes"), lines)
        suffix = ["Use arrows + Enter to select; Esc to go back."]
        return DecisionResult(
            summary=None,
            requests=[
                DecisionRequest(kind="log", message=CLEAR_SCREEN),
                DecisionRequest(
                    kind="prompt",
                    message="",
                    options=options,
                    default="1",
                    input_mode="menu_grid",
                    payload={"prefix": prefix, "suffix": suffix, "cols": 1, "col_width": 48, "roulette": True},
                ),
            ],
            done=False,
            data=self._serialize_state(),
        )

    def _handle_stats_choice(self, value: str) -> None:
        if value == "1":
            self.step += 1
            return
        if value == "2":
            if self.state.rerolls_left > 0:
                self.state.rerolls_left -= 1
                self.state.stats = roll_stats(self.state.position)
            return
        # Ignore other inputs (including Esc) to keep players from backing out post-roll.

    # --- Step 4: growth style ---
    def _step_growth_style(self) -> DecisionResult:
        if "growth_phase" not in self._scratch:
            self._scratch["growth_phase"] = "choose"
        phase = self._scratch["growth_phase"]

        if self.state.position == "Pitcher":
            styles = ["Heat Seeker", "Corner Artist", "Spin Doctor", "Balanced Pitcher"]
        elif self.state.position == "Catcher":
            styles = ["Iron Wall", "Battery Bomber", "Field General", "Balanced Catcher"]
        elif self.state.position == "Infielder":
            styles = ["Glove Wizard", "Corner Crusher", "Table Setter", "Balanced Infielder"]
        else:  # Outfielder
            styles = ["Range Rover", "Laser Show", "Gap Hunter", "Balanced Outfielder"]
        self._scratch["growth_styles"] = styles

        if phase == "choose":
            lines = [f"Select Growth Style for {self.state.specific_pos} (Esc to go back)"]
            self._awaiting = "growth_pick"
            prefix = self._with_banner(STEP_TITLES.get(4, "Choose Growth Style"), lines)
            suffix = ["Use arrows + Enter to preview; Esc to go back."]
            return DecisionResult(
                summary=None,
                requests=[
                    DecisionRequest(kind="log", message=CLEAR_SCREEN),
                    DecisionRequest(
                        kind="prompt",
                        message="",
                        options=styles,
                        default="1",
                        input_mode="menu_grid",
                        payload={"prefix": prefix, "suffix": suffix, "cols": 2, "col_width": 38},
                    ),
                ],
                done=False,
                data=self._serialize_state(),
            )

        if phase == "confirm":
            style = self.state.growth_style or ""
            detail_lines = _growth_detail_lines(style)
            lines = [f"Selected Growth Style: {style}", ""] + detail_lines
            lines.append("")
            self._awaiting = "growth_confirm"
            prefix = self._with_banner(STEP_TITLES.get(4, "Choose Growth Style"), lines)
            suffix = ["Use arrows + Enter to confirm; Esc to go back."]
            return DecisionResult(
                summary=None,
                requests=[
                    DecisionRequest(kind="log", message=CLEAR_SCREEN),
                    DecisionRequest(
                        kind="prompt",
                        message="",
                        options=["Confirm and continue"],
                        default="1",
                        input_mode="menu_grid",
                        payload={"prefix": prefix, "suffix": suffix, "cols": 1, "col_width": 42},
                    ),
                ],
                done=False,
                data=self._serialize_state(),
            )

        # done
        self._scratch.pop("growth_phase", None)
        self.step += 1
        return self.advance()

    def _handle_growth_pick(self, value: str) -> None:
        styles = self._scratch.get("growth_styles", [])
        if value == "0":
            self.step = max(0, self.step - 1)
            return
        if not value.isdigit():
            return
        idx = int(value) - 1
        if 0 <= idx < len(styles):
            self.state.growth_style = styles[idx]
            self._scratch["growth_phase"] = "confirm"

    def _handle_growth_confirm(self, value: str) -> None:
        if value == "0":
            self._scratch["growth_phase"] = "choose"
            return
        if value == "1":
            self._scratch.pop("growth_phase", None)
            self.step += 1

    # --- Step 5: hometown ---
    def _step_hometown(self) -> DecisionResult:
        # simplified: pick prefecture and optional city by free text search
        prefectures = get_prefecture_catalog(self.session)
        self._scratch["prefectures"] = prefectures
        if not prefectures:
            self.state.hometown = "Tokyo"
            self.state.prefecture_choice = "Tokyo"
            self.step += 1
            return self.advance()
        if "hometown_phase" not in self._scratch:
            self._scratch["hometown_phase"] = "pref"
        phase = self._scratch["hometown_phase"]
        if phase == "pref":
            self._awaiting = "hometown_pref"
            prefix = self._with_banner(
                STEP_TITLES.get(5, "Pick Hometown"), ["Select Prefecture (Esc to go back)"]
            )
            suffix = ["Use arrows + Enter to select; Esc to go back."]
            return DecisionResult(
                summary=None,
                requests=[
                    DecisionRequest(kind="log", message=CLEAR_SCREEN),
                    DecisionRequest(
                        kind="prompt",
                        message="",
                        options=prefectures,
                        default="1",
                        input_mode="menu_grid",
                        payload={"prefix": prefix, "suffix": suffix, "cols": 3, "col_width": 24},
                    ),
                ],
                done=False,
                data=self._serialize_state(),
            )
        if phase == "tokyo_side":
            self._awaiting = "hometown_tokyo_side"
            prefix = self._with_banner(
                STEP_TITLES.get(5, "Pick Hometown"), ["Prefecture: Tokyo", "Choose East or West Tokyo (Esc to go back)"]
            )
            suffix = ["Use arrows + Enter to select; Esc to go back."]
            options = ["East Tokyo (23 Wards)", "West Tokyo (Tama/Islands)"]
            return DecisionResult(
                summary=None,
                requests=[
                    DecisionRequest(kind="log", message=CLEAR_SCREEN),
                    DecisionRequest(
                        kind="prompt",
                        message="",
                        options=options,
                        default="1",
                        input_mode="menu_grid",
                        payload={"prefix": prefix, "suffix": suffix, "cols": 1, "col_width": 40},
                    ),
                ],
                done=False,
                data=self._serialize_state(),
            )
        if phase == "city":
            pref = self.state.prefecture_choice or ""
            cities = _load_cities_for_prefecture(self.session, pref)
            side = None
            side_label = ""
            if pref == "Tokyo":
                side = self._scratch.get("tokyo_side")
                side_label = f" ({side.title()})" if side else ""
                cities = _filter_tokyo_cities(cities, side)
            city_labels = [
                f"{c.get('name', '--')} ({c.get('school_count', '')})" if c.get("school_count") else c.get("name", "--")
                for c in cities
            ]
            self._awaiting = "hometown_city"
            prefix = self._with_banner(
                STEP_TITLES.get(5, "Pick Hometown"), [f"Prefecture: {pref}{side_label}", "Select a city or skip (Esc to go back)"]
            )
            suffix = ["Use arrows + Enter to select; Esc to skip."]
            return DecisionResult(
                summary=None,
                requests=[
                    DecisionRequest(kind="log", message=CLEAR_SCREEN),
                    DecisionRequest(
                        kind="prompt",
                        message="",
                        options=city_labels if city_labels else ["Skip"],
                        default="1",
                        input_mode="menu_grid",
                        payload={"prefix": prefix, "suffix": suffix, "cols": 4, "col_width": 22},
                    ),
                ],
                done=False,
                data=self._serialize_state(),
            )
        # done
        self._scratch.pop("hometown_phase", None)
        self._scratch.pop("tokyo_side", None)
        self.step += 1
        return self.advance()

    def _handle_hometown_pref(self, value: str) -> None:
        val = value.strip()
        prefectures = self._scratch.get("prefectures") or get_prefecture_catalog(self.session)
        if value == "0":
            self.step = max(0, self.step - 1)
            return

        if val.isdigit():
            idx = int(val) - 1
            if 0 <= idx < len(prefectures):
                self.state.prefecture_choice = prefectures[idx]
                if self.state.prefecture_choice == "Tokyo":
                    self._scratch["tokyo_side"] = None
                    self._scratch["hometown_phase"] = "tokyo_side"
                else:
                    self._scratch.pop("tokyo_side", None)
                    self._scratch["hometown_phase"] = "city"
            return

        matches = [p for p in prefectures if val.lower() in p.lower()] if val else prefectures
        if not matches:
            return
        self.state.prefecture_choice = matches[0]
        if self.state.prefecture_choice == "Tokyo":
            self._scratch["tokyo_side"] = None
            self._scratch["hometown_phase"] = "tokyo_side"
        else:
            self._scratch.pop("tokyo_side", None)
            self._scratch["hometown_phase"] = "city"

    def _handle_hometown_tokyo_side(self, value: str) -> None:
        if value == "0":
            self._scratch["hometown_phase"] = "pref"
            return
        if not value.isdigit():
            return
        idx = int(value) - 1
        if idx == 0:
            self._scratch["tokyo_side"] = "east"
            self._scratch["hometown_phase"] = "city"
        elif idx == 1:
            self._scratch["tokyo_side"] = "west"
            self._scratch["hometown_phase"] = "city"

    def _handle_hometown_city(self, value: str) -> None:
        pref = self.state.prefecture_choice or ""
        city = value.strip()
        cities = _load_cities_for_prefecture(self.session, pref)
        if pref == "Tokyo":
            cities = _filter_tokyo_cities(cities, self._scratch.get("tokyo_side"))
        side = self._scratch.get("tokyo_side") if pref == "Tokyo" else None
        if not cities:
            if pref == "Tokyo" and side:
                self.state.hometown = f"{pref} ({side.title()})"
            else:
                self.state.hometown = pref
            self._scratch.pop("hometown_phase", None)
            self.step += 1
            return
        if city:
            match = None
            if city.isdigit():
                idx = int(city) - 1
                if 0 <= idx < len(cities):
                    match = cities[idx]
            if match is None:
                match = next((c for c in cities if city.lower() in c['name'].lower()), None)
            if match:
                if pref == "Tokyo" and side:
                    self.state.hometown = f"{pref} ({side.title()}) — {match['name']}"
                else:
                    self.state.hometown = f"{pref} — {match['name']}"
            else:
                if pref == "Tokyo" and side:
                    self.state.hometown = f"{pref} ({side.title()}) — {city}"
                else:
                    self.state.hometown = f"{pref} — {city}"
        else:
            if pref == "Tokyo" and side:
                self.state.hometown = f"{pref} ({side.title()})"
            else:
                self.state.hometown = pref
        self._scratch.pop("hometown_phase", None)
        self._scratch.pop("tokyo_side", None)
        self.step += 1

    # --- Step 6: school ---
    def _step_school(self) -> DecisionResult:
        phase = self._scratch.get("school_phase", "choose")
        candidate_idx = self._scratch.get("school_candidate_idx")
        hometown = self.state.hometown or ''
        pref = self.state.prefecture_choice
        if not pref and hometown:
            pref = hometown.split('—')[0].strip()
        pref = pref or "Tokyo"

        city = None
        if '—' in hometown:
            city = hometown.split('—', 1)[1].strip()

        base_query = self.session.query(School).filter(School.prefecture == pref)
        offers = []
        if city:
            offers = (
                base_query.filter(School.city_name == city)
                .order_by(func.random())
                .limit(5)
                .all()
            )
        if not offers:
            offers = base_query.order_by(func.random()).limit(5).all()
        if not offers:
            offers = self.session.query(School).order_by(func.random()).limit(5).all()

        self._scratch["school_offers"] = offers
        labels = [f"{t.name} (Rank: {t.prestige})" for t in offers]

        if phase == "confirm" and candidate_idx is not None and 0 <= candidate_idx < len(offers):
            pick = offers[candidate_idx]
            lines = [
                f"Confirm School: {pick.name}",
                f"Rank: {pick.prestige}",
                f"Prefecture: {pick.prefecture} | City: {getattr(pick, 'city_name', '--')}",
            ]
            prefix = self._with_banner(STEP_TITLES.get(6, "Select School"), lines)
            suffix = ["Use arrows + Enter to confirm or change."]
            self._awaiting = "school_confirm"
            return DecisionResult(
                summary=None,
                requests=[
                    DecisionRequest(kind="log", message=CLEAR_SCREEN),
                    DecisionRequest(
                        kind="prompt",
                        message="",
                        options=["Confirm", "Change"],
                        default="1",
                        input_mode="menu_grid",
                        payload={"prefix": prefix, "suffix": suffix, "cols": 2, "col_width": 22},
                    ),
                ],
                done=False,
                data=self._serialize_state(),
            )

        self._awaiting = "school_pick"
        prefix = self._with_banner(
            STEP_TITLES.get(6, "Select School"),
            [f"Offers from {pref}{' — ' + city if city else ''}:"]
        )
        suffix = ["Use arrows + Enter to select; Esc to go back."]
        return DecisionResult(
            summary=None,
            requests=[
                DecisionRequest(kind="log", message=CLEAR_SCREEN),
                DecisionRequest(
                    kind="prompt",
                    message="",
                    options=labels,
                    default="1",
                    input_mode="menu_grid",
                    payload={
                        "prefix": prefix,
                        "suffix": suffix,
                        "cols": 1,
                        "col_width": 70,
                    },
                ),
            ],
            done=False,
            data=self._serialize_state(),
        )

    def _handle_school_pick(self, value: str) -> None:
        offers: List[School] = self._scratch.get("school_offers", [])
        if value == "0":
            self.step = max(0, self.step - 1)
            return
        if not value.isdigit():
            return
        idx = int(value) - 1
        if 0 <= idx < len(offers):
            self._scratch["school_candidate_idx"] = idx
            self._scratch["school_phase"] = "confirm"

    def _handle_school_confirm(self, value: str) -> None:
        offers: List[School] = self._scratch.get("school_offers", [])
        idx = self._scratch.get("school_candidate_idx")
        if value == "2":
            self._scratch["school_phase"] = "choose"
            return
        if value not in {"1", "Confirm", "confirm"} or idx is None or not (0 <= idx < len(offers)):
            return
        self.state.school = offers[idx]
        acad_skill, last_score = roll_academic_profile(self.state.hometown, self.state.school)
        self.state.stats = self.state.stats or {}
        self.state.stats['academic_skill'] = acad_skill
        self.state.stats['test_score'] = last_score
        self._scratch.pop("school_phase", None)
        self._scratch.pop("school_candidate_idx", None)
        self.step += 1

    # --- Step 7: pitch arsenal ---
    def _step_pitch_arsenal(self) -> DecisionResult:
        if self.state.position != "Pitcher":
            self.state.pitch_arsenal = []
            self.step += 1
            return self.advance()
        current_count = len(self.state.pitch_arsenal)
        rec_lines = _pitch_recommendations(self.state.pitch_arsenal, (self.state.stats or {}).get("arm_slot"))
        header = self._with_banner(
            STEP_TITLES.get(7, "Configure Pitch Arsenal"),
            [
                "Select Pitches (Esc to go back)",
                f"Current: ({current_count}/{MAX_PITCHES}) Need {MIN_PITCHES}-{MAX_PITCHES} total.",
                "",
                "Recommended:",
                *([f"- {line}" for line in rec_lines] if rec_lines else ["- Pick a heater + breaker + changeup."]),
                "",
            ],
        )
        self._awaiting = "pitch_entry"
        return DecisionResult(
            summary=None,
            requests=[
                DecisionRequest(kind="log", message=CLEAR_SCREEN),
                DecisionRequest(
                    kind="prompt",
                    message="",
                    options=PITCH_SELECTION_POOL,
                    default="",
                    input_mode="pitch_grid",
                    payload={
                        "header": header,
                        "selected": list(self.state.pitch_arsenal),
                    },
                ),
            ],
            done=False,
            data=self._serialize_state(),
        )

    def _handle_pitch_entry(self, value: str) -> None:
        raw_tokens = [p.strip() for p in (value or "").split(',') if p.strip()]
        if len(raw_tokens) == 1 and raw_tokens[0] == "0":
            self.step = max(0, self.step - 1)
            return

        resolved: List[str] = []
        for tok in raw_tokens:
            if tok.isdigit():
                idx = int(tok) - 1
                if 0 <= idx < len(PITCH_SELECTION_POOL):
                    resolved.append(PITCH_SELECTION_POOL[idx])
                continue
            resolved.append(tok)

        # Blank input means defaults
        if not raw_tokens:
            resolved = list(DEFAULT_PITCH_ARSENAL)

        valid, message = _validate_pitch_selection(resolved)
        if not valid:
            self._scratch["pitch_error"] = message
            return

        self.state.pitch_arsenal = _dedupe_preserve_order(resolved)
        self.step += 1

    # --- Step 8: finalize ---
    def _step_finalize(self) -> DecisionResult:
        summary_lines = [
            f"Name:   {self.state.last_name} {self.state.first_name}",
            f"Role:   {self.state.specific_pos}",
            f"Style:  {self.state.growth_style}",
            f"Hometown: {self.state.hometown}",
            f"School: {(self.state.school.name if self.state.school else '--')}",
        ]
        acad_skill = (self.state.stats or {}).get('academic_skill', '??')
        last_score = (self.state.stats or {}).get('test_score', '??')
        summary_lines.append(f"Academics: Skill {acad_skill} / Latest Test {last_score}")
        stats = self.state.stats or {}
        if self.state.position == "Pitcher":
            arm_slot = stats.get('arm_slot') or "Three-Quarters"
            summary_lines.append(f"Arm Slot: {arm_slot}")
            trait_txt = "Unlocked" if self.state.starter_trait else "--"
            summary_lines.append(f"Starter Trait: {trait_txt}")
            summary_lines.append(
                "Pitching: "
                f"V{stats.get('velocity','--')} | C{stats.get('control','--')} | "
                f"M{stats.get('movement','--')} | St{stats.get('stamina','--')}"
            )
            arsenal = _dedupe_preserve_order(self.state.pitch_arsenal)
            summary_lines.append(f"Pitches: {', '.join(arsenal) if arsenal else '--'}")
        else:
            line = "Offense/Defense: " + " | ".join(
                [
                    f"Con{stats.get('contact','--')}",
                    f"Pow{stats.get('power','--')}",
                    f"Spd{stats.get('speed','--')}",
                    f"Fld{stats.get('fielding','--')}",
                    f"Arm{stats.get('throwing','--')}",
                    f"Velo{stats.get('velocity','--')}",
                ]
            )
            if self.state.position == "Catcher":
                line += f" | Wall{stats.get('catcher_ability','--')}"
            summary_lines.append(line)
        err = self._scratch.pop("finalize_error", None)
        summary_lines.append("")
        if err:
            summary_lines.append(f"Error creating player: {err}")
            summary_lines.append("")
        self._awaiting = "final_choice"
        prefix = self._with_banner(STEP_TITLES.get(8, "Confirm Profile"), summary_lines)
        suffix = ["Use arrows + Enter to start; Esc to go back."]
        return DecisionResult(
            summary=None,
            requests=[
                DecisionRequest(kind="log", message=CLEAR_SCREEN),
                DecisionRequest(
                    kind="prompt",
                    message="",
                    options=["Start Game"],
                    default="1",
                    input_mode="menu_grid",
                    payload={"prefix": prefix, "suffix": suffix, "cols": 1, "col_width": 24},
                ),
            ],
            done=False,
            data=self._serialize_state(),
        )

    def _handle_final_choice(self, value: str) -> None:
        if value == "0":
            self.step = max(0, self.step - 1)
            return
        if value in {"0", "1", "WIN", "LOSE"}:
            # Persist player to DB and mark flow complete.
            try:
                if not self.state.position or not self.state.stats or not self.state.school:
                    raise ValueError("Missing required data (position/stats/school) to create player.")
                data = {
                    "first_name": self.state.first_name,
                    "last_name": self.state.last_name,
                    "position": self.state.position,
                    "specific_pos": self.state.specific_pos,
                    "growth_style": self.state.growth_style,
                    "stats": self.state.stats or {},
                    "hometown": self.state.hometown,
                    "school": self.state.school,
                    "pitch_arsenal": self.state.pitch_arsenal,
                    "starter_trait": self.state.starter_trait,
                }
                player_id = commit_player_to_db(self.session, data)
                self._scratch["created_player_id"] = player_id
            except Exception as exc:
                # Stay on finalize step and surface an error message on next render.
                self._scratch["finalize_error"] = str(exc)
                return

            self.step += 1
    # --------- terminal ---------
    def is_complete(self) -> bool:
        return self.step > 8 and "created_player_id" in self._scratch

    def result(self) -> Optional[int]:
        return self._scratch.get("created_player_id")


def drive_create_player(session: Session, io: Optional[IOInterface] = None) -> Optional[int]:
    """Compatibility adapter that drives the decision engine using IOInterface."""

    def _read_with_esc(prompt: str, default: str = "") -> str:
        # Windows-only single-key capture to allow ESC for back.
        if os.name == "nt" and 'msvcrt' in sys.modules:
            sys.stdout.write(prompt)
            sys.stdout.flush()
            buf: List[str] = []
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return "".join(buf) if buf else default
                if ch == "\x1b":  # ESC
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return "__ESC__"
                if ch in ("\x08", "\x7f"):  # backspace
                    if buf:
                        buf.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue
                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
        # Fallback: standard line input
        try:
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            return default

    def _interactive_select_grid(request: DecisionRequest) -> str:
        """Grid-based arrow menu; renders a fresh screen each move."""
        options = request.options or []
        payload = request.payload or {}
        cols = int(payload.get("cols", 3))
        col_width = int(payload.get("col_width", 26))
        prefix = payload.get("prefix", [])
        suffix = payload.get("suffix", [])
        base = 1

        def render(idx: int) -> None:
            block_lines = list(prefix)
            block_lines.extend(_options_grid(options, cols=cols, col_width=col_width, highlight=idx))
            block_lines.extend(suffix)
            sys.stdout.write(CLEAR_SCREEN)
            sys.stdout.write("\n".join(block_lines) + "\n")
            sys.stdout.flush()

        sel = 0
        if request.default.isdigit():
            d_idx = int(request.default) - base
            if 0 <= d_idx < len(options):
                sel = d_idx
        render(sel)

        rows = (len(options) + cols - 1) // cols

        def move(idx: int, dr: int, dc: int) -> int:
            row, col = divmod(idx, cols)
            start_row, start_col = row, col
            while True:
                row = (row + dr) % rows
                col = (col + dc) % cols
                nxt_idx = row * cols + col
                if nxt_idx < len(options):
                    return nxt_idx
                if (row, col) == (start_row, start_col):
                    return idx

        def handle_enter() -> str:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return str(base + sel)

        def handle_esc() -> str:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "__ESC__"

        if os.name == "nt" and 'msvcrt' in sys.modules:
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    return handle_enter()
                if ch == "\x1b":
                    return handle_esc()
                if ch in ("\xe0", "\x00"):
                    nxt = msvcrt.getwch()
                    if nxt == "H":
                        sel = move(sel, -1, 0)  # up
                        render(sel)
                    elif nxt == "P":
                        sel = move(sel, 1, 0)  # down
                        render(sel)
                    elif nxt == "K":
                        sel = move(sel, 0, -1)  # left
                        render(sel)
                    elif nxt == "M":
                        sel = move(sel, 0, 1)  # right
                        render(sel)
                    continue
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ("\r", "\n"):
                        return handle_enter()
                    if ch == "\x1b":
                        seq = sys.stdin.read(2)
                        if seq == "[A":  # up
                            sel = move(sel, -1, 0)
                            render(sel)
                        elif seq == "[B":  # down
                            sel = move(sel, 1, 0)
                            render(sel)
                        elif seq == "[C":  # right
                            sel = move(sel, 0, 1)
                            render(sel)
                        elif seq == "[D":  # left
                            sel = move(sel, 0, -1)
                            render(sel)
                        else:
                            return handle_esc()
                        continue
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return handle_enter()

    def _interactive_pitch_grid(request: DecisionRequest) -> str:
        """Multi-select pitch picker with checkboxes and live count."""
        options = request.options or []
        payload = request.payload or {}
        selected: List[str] = list(payload.get("selected", []))
        base_header: List[str] = list(payload.get("header", []))
        cols = 2
        col_width = 36
        rows = (len(options) + cols - 1) // cols

        def move(idx: int, dr: int, dc: int) -> int:
            row, col = divmod(idx, cols)
            start_row, start_col = row, col
            while True:
                row = (row + dr) % rows
                col = (col + dc) % cols
                nxt = row * cols + col
                if nxt < len(options):
                    return nxt
                if (row, col) == (start_row, start_col):
                    return idx

        def render(idx: int, error: str = "") -> None:
            sys.stdout.write(CLEAR_SCREEN)
            lines = list(base_header) if base_header else []
            count_line = f"Current: ({len(selected)}/{MAX_PITCHES}) Need {MIN_PITCHES}-{MAX_PITCHES} total."
            if len(lines) >= 2:
                lines[1] = count_line
            else:
                lines.append(count_line)
            lines.append("")
            lines.extend(_pitch_grid(options, selected, cols=cols, col_width=col_width, highlight=idx))
            lines.append("Space = toggle • Enter = confirm • Esc = back")
            if error:
                lines.append(error)
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()

        def toggle(idx: int) -> Optional[str]:
            name = options[idx]
            if name in selected:
                selected.remove(name)
                return None
            if len(selected) >= MAX_PITCHES:
                return f"Max {MAX_PITCHES} pitches. Remove one first."
            selected.append(name)
            return None

        def handle_enter() -> str:
            if len(selected) < MIN_PITCHES:
                return "__ERROR__"
            return ",".join(selected)

        sel = 0
        if selected:
            try:
                sel = options.index(selected[0])
            except ValueError:
                sel = 0
        render(sel)

        if os.name == "nt" and 'msvcrt' in sys.modules:
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    result = handle_enter()
                    if result == "__ERROR__":
                        render(sel, error=f"Select at least {MIN_PITCHES} pitches.")
                        continue
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return result
                if ch == " ":
                    msg = toggle(sel)
                    render(sel, error=msg or "")
                    continue
                if ch == "\x1b":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return "__ESC__"
                if ch in ("\xe0", "\x00"):
                    nxt = msvcrt.getwch()
                    if nxt == "H":  # up
                        sel = move(sel, -1, 0)
                        render(sel)
                    elif nxt == "P":  # down
                        sel = move(sel, 1, 0)
                        render(sel)
                    elif nxt == "K":  # left
                        sel = move(sel, 0, -1)
                        render(sel)
                    elif nxt == "M":  # right
                        sel = move(sel, 0, 1)
                        render(sel)
                    continue
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ("\r", "\n"):
                        result = handle_enter()
                        if result == "__ERROR__":
                            render(sel, error=f"Select at least {MIN_PITCHES} pitches.")
                            continue
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        return result
                    if ch == " ":
                        msg = toggle(sel)
                        render(sel, error=msg or "")
                        continue
                    if ch == "\x1b":
                        seq = sys.stdin.read(2)
                        if seq == "[A":  # up
                            sel = move(sel, -1, 0)
                            render(sel)
                        elif seq == "[B":  # down
                            sel = move(sel, 1, 0)
                            render(sel)
                        elif seq == "[D":  # left
                            sel = move(sel, 0, -1)
                            render(sel)
                        elif seq == "[C":  # right
                            sel = move(sel, 0, 1)
                            render(sel)
                        else:
                            sys.stdout.write("\n")
                            sys.stdout.flush()
                            return "__ESC__"
                        continue
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return handle_enter()

    def _interactive_starter_spin(request: DecisionRequest) -> str:
        """Roulette-style animation for the starter trait roll."""
        payload = request.payload or {}
        header_lines: List[str] = list(payload.get("header", []))
        odds = float(payload.get("odds", 0.35))
        label = payload.get("label", "Starter Trait")
        frames = [
            "| ☆ | ★ | ☆ |",
            "| ★ | ☆ | ★ |",
            "| ☆ | ☆ | ★ |",
            "| ★ | ★ | ☆ |",
        ]

        def show(lines: List[str]) -> None:
            sys.stdout.write(CLEAR_SCREEN)
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()

        def wait_for_enter_or_esc() -> Optional[str]:
            if os.name == "nt" and 'msvcrt' in sys.modules:
                while True:
                    ch = msvcrt.getwch()
                    if ch in ("\r", "\n"):
                        return "enter"
                    if ch == "\x1b":
                        return "esc"
            else:
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    while True:
                        ch = sys.stdin.read(1)
                        if ch in ("\r", "\n"):
                            return "enter"
                        if ch == "\x1b":
                            return "esc"
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
            return None

        # Prompt to start
        start_lines = list(header_lines)
        start_lines.append(f"Press Enter to spin for {label}; Esc to go back.")
        show(start_lines)
        action = wait_for_enter_or_esc()
        if action == "esc":
            return "__ESC__"

        # Run animation
        spins = random.randint(18, 28)
        for i in range(spins):
            frame = frames[i % len(frames)]
            lines = list(header_lines)
            lines.append("Spinning...")
            lines.append(frame)
            show(lines)
            time.sleep(0.05 + (i / spins) * 0.03)

        win = random.random() < odds
        result_text = "WIN! Starter Trait unlocked." if win else "Missed. No Starter Trait (for now)."
        result_lines = list(header_lines)
        result_lines.append(result_text)
        result_lines.append("Press Enter to continue.")
        show(result_lines)
        wait_for_enter_or_esc()
        return "WIN" if win else "LOSE"

    def _interactive_yes_no(request: DecisionRequest) -> str:
        """Inline YES/NO arrow prompt; clears screen on each movement."""
        options = request.options or ["YES", "NO"]
        payload = request.payload or {}
        prefix = payload.get("prefix", [])
        suffix = payload.get("suffix", [])
        base = 1

        def render(idx: int) -> None:
            block_lines = list(prefix)
            if block_lines:
                block_lines.append("")
            line = "    ".join([f"> {opt}" if i == idx else f"  {opt}" for i, opt in enumerate(options)])
            block_lines.append(line)
            block_lines.extend(suffix)
            sys.stdout.write(CLEAR_SCREEN)
            sys.stdout.write("\n".join(block_lines) + "\n")
            sys.stdout.flush()

        sel = 0
        if request.default.isdigit():
            d_idx = int(request.default) - base
            if 0 <= d_idx < len(options):
                sel = d_idx
        render(sel)

        def handle_enter() -> str:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return str(base + sel)

        def handle_esc() -> str:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "__ESC__"

        if os.name == "nt" and 'msvcrt' in sys.modules:
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    return handle_enter()
                if ch == "\x1b":
                    return handle_esc()
                if ch in ("\xe0", "\x00"):
                    nxt = msvcrt.getwch()
                    if nxt in ("H", "K"):
                        sel = (sel - 1) % len(options)
                        render(sel)
                    elif nxt in ("P", "M"):
                        sel = (sel + 1) % len(options)
                        render(sel)
                    continue
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ("\r", "\n"):
                        return handle_enter()
                    if ch == "\x1b":
                        seq = sys.stdin.read(2)
                        if seq in ("[A", "[D"):
                            sel = (sel - 1) % len(options)
                            render(sel)
                        elif seq in ("[B", "[C"):
                            sel = (sel + 1) % len(options)
                            render(sel)
                        else:
                            return handle_esc()
                        continue
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return handle_enter()

    def _interactive_select(message: str, options: List[str], default: str = "") -> str:
        """Arrow-key menu for selection; returns index+1 as string, ESC -> __ESC__."""
        base = 1

        def render(idx: int) -> None:
            lines = [message]
            for i, opt in enumerate(options):
                pointer = ">" if i == idx else " "
                lines.append(f" {pointer} {opt}")
            block = "\n".join(lines)
            if render.called:
                sys.stdout.write(f"\033[{len(lines)}F")
            render.called = True
            sys.stdout.write(block + "\n")
            sys.stdout.flush()

        render.called = False  # type: ignore
        sel = 0
        if default.isdigit():
            d_idx = int(default) - base
            if 0 <= d_idx < len(options):
                sel = d_idx
        render(sel)

        def handle_enter() -> str:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return str(base + sel)

        def handle_esc() -> str:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "__ESC__"

        if os.name == "nt" and 'msvcrt' in sys.modules:
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    return handle_enter()
                if ch == "\x1b":
                    return handle_esc()
                if ch in ("\xe0", "\x00"):
                    nxt = msvcrt.getwch()
                    if nxt in ("H", "K"):
                        sel = (sel - 1) % len(options)
                        render(sel)
                    elif nxt in ("P", "M"):
                        sel = (sel + 1) % len(options)
                        render(sel)
                    continue
                # ignore others
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ("\r", "\n"):
                        return handle_enter()
                    if ch == "\x1b":
                        seq = sys.stdin.read(2)
                        if seq in ("[A", "[D"):
                            sel = (sel - 1) % len(options)
                            render(sel)
                        elif seq in ("[B", "[C"):
                            sel = (sel + 1) % len(options)
                            render(sel)
                        else:
                            return handle_esc()
                        continue
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return handle_enter()

    engine = CreatePlayerEngine(session)
    response: Optional[str] = None
    while True:
        result = engine.advance(response)
        response = None
        for request in result.requests:
            if request.kind == "log":
                if io:
                    io.log(request.message, level=request.level)
                else:
                    print(request.message)
            elif request.kind == "prompt":
                if io:
                    response = io.prompt(request.message, options=request.options)
                else:
                    if request.input_mode == "menu_grid":
                        response = _interactive_select_grid(request)
                    elif request.input_mode == "pitch_grid":
                        response = _interactive_pitch_grid(request)
                    elif request.input_mode == "starter_spin":
                        response = _interactive_starter_spin(request)
                    elif request.input_mode == "binary_yes_no":
                        response = _interactive_yes_no(request)
                    elif request.options:
                        response = _interactive_select(request.message, request.options, default=request.default)
                    else:
                        response = _read_with_esc(request.message, default=request.default)
        if result.done and engine.result() is not None:
            return engine.result()
        if engine.is_complete():
            return engine.result()


def create_hero(session: Session, *, use_tui: Optional[bool] = None) -> Optional[int]:
    """
    Entry point for character creation. Uses Textual TUI when enabled.
    """
    env_raw = os.environ.get("USE_TUI_CREATOR", "")
    env_forced = env_raw.lower() in {"1", "true", "yes"}
    if use_tui is None:
        # Default to TUI if available; env can force on/off.
        use_tui = env_forced or True
    if use_tui:
        try:
            import importlib
            run_tui_create_player = importlib.import_module("ui.tui_create_player").run_tui_create_player
        except Exception:
            if env_forced:
                print("TUI creator unavailable; aborting character creation.")
                return None
            else:
                print("TUI creator unavailable; falling back to console creator.")
                return drive_create_player(session)
        else:
            res = run_tui_create_player(session)
            if res is not None:
                return res
            if env_forced:
                print("TUI creator cancelled or failed; aborting character creation.")
                return None
            print("TUI creator cancelled; falling back to console creator.")
            return drive_create_player(session)
    return drive_create_player(session)


if __name__ == "__main__":
    from database.setup_db import get_session

    temp_session = get_session()
    try:
        create_hero(temp_session)
    finally:
        temp_session.close()
