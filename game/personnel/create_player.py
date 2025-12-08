import sys
import os
import random
import time
from typing import Optional, List, Tuple, Dict, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.io_interface import IOInterface

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.setup_db import School, Player, PitchRepertoire
from database.populate_japan import roll_arm_slot
from player_roles.two_way import roll_two_way_profile
from game.systems.academic_system import roll_academic_profile
from game.personnel.relationship_manager import seed_relationships
from game.personnel.personality import roll_player_personality
from game.personnel.player_generation import maybe_assign_bad_trait
from game.mechanics.trait_logic import grant_user_creation_trait_rolls
from game.mechanics.pitch_mastery import mastery_level_for_xp
from match_engine.pitch_definitions import PITCH_TYPES

# --- GROWTH STYLE DEFINITIONS ---
GROWTH_STYLE_INFO = {
    "Power Pitcher": {"desc": "Overwhelm batters with raw heat.", "pros": "+Vel, +Sta", "cons": "-Ctrl"},
    "Technical Pitcher": {"desc": "Precision over power.", "pros": "+Ctrl, +Brk", "cons": "-Vel"},
    "Fierce Pitcher": {"desc": "Thrives under pressure.", "pros": "+Guts, +Vel(Clutch)", "cons": "-Stability"},
    "Marathon Pitcher": {"desc": "Built to throw 150 pitches.", "pros": "+Stamina, +Stability", "cons": "-Vel cap"},
    "Offensive Catcher": {"desc": "Big bat behind the plate.", "pros": "+Pwr, +Con", "cons": "-Def"},
    "Defensive General": {"desc": "Field commander.", "pros": "+Def, +Trust", "cons": "-Batting"},
    "Power Hitter": {"desc": "Swing for the fences.", "pros": "+Pwr, +Intimidation", "cons": "-Con, -Spd"},
    "Speedster": {"desc": "Chaos on the basepaths.", "pros": "+Spd, +Fld", "cons": "-Pwr"},
    "Defensive Specialist": {"desc": "Vacuum cleaner in the field.", "pros": "+Fld, +Reaction", "cons": "-Batting"},
    "Balanced": {"desc": "Jack of all trades.", "pros": "No weakness", "cons": "No specialty"}
}

STEP_TITLES = {
    0: "Name Entry",
    1: "Select Position",
    2: "Starter Trait Gacha",
    3: "Roll Base Attributes",
    4: "Choose Growth Style",
    5: "Pick Hometown",
    6: "Select School",
    7: "Configure Pitch Arsenal",
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


def _dedupe_preserve_order(items: Optional[List[str]]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items or []:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result

_PREFECTURE_CACHE: Optional[List[str]] = None
_CITY_CACHE: Dict[str, List[Dict[str, Any]]] = {}


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
    except Exception as exc:
        print(f"Prefecture lookup failed: {exc}")
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
    except Exception as exc:
        print(f"City lookup failed for {prefecture}: {exc}")
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
        label = f"{idx:>2}. {entry['name']} ({entry['school_count']})"
        print(label.ljust(col_width), end="")
        if idx % columns == 0:
            print()
    if len(cities) % columns != 0:
        print()
    print(f"Cities with active programs: {len(cities)}")


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


def _render_creation_banner(step: int, data: dict, subtitle: str) -> None:
    # Deprecated direct rendering retained for legacy CLI usage.
    stage_index = min(step, TOTAL_STEPS - 1)
    stage = stage_index + 1
    print(f"{'═' * 84}")
    title = f"CHARACTER CREATION  |  STEP {stage}/{TOTAL_STEPS}"
    print(title.center(84))
    print(subtitle.center(84))
    print(f"{'═' * 84}")

    full_name = " ".join(part for part in [data['last_name'], data['first_name']] if part).strip()
    summary = [
        f"Name: {full_name or '--'}",
        f"Focus: {data.get('specific_pos') or '--'} ({data.get('position') or '--'})",
        f"Hometown: {data.get('hometown') or '--'}",
        f"School: {(data.get('school').name if data.get('school') else '--')}"
    ]
    for line in summary:
        print(line.ljust(84))
    print("─" * 84)


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
        ]
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

    # ---------------------------
    #  Player Skill Stats
    # ---------------------------
    stats['stamina'] = get_val()

    stats['control'] = get_val() if position == "Pitcher" else 10
    stats['movement'] = get_val() if position == "Pitcher" else 0

    stats['power'] = get_val()
    stats['contact'] = get_val()
    stats['speed'] = get_val()
    stats['fielding'] = get_val()
    stats['throwing'] = get_val()

    if position == "Pitcher":
        stats['velocity'] = random.randint(125, 138) + (10 if is_monster else 0)
        stats['arm_slot'] = roll_arm_slot("pitching")
    else:
        stats['velocity'] = 0
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
    else:
        clean_stats.setdefault('catcher_ability', 0)

    growth_tag = clean_stats.pop("growth_tag", None)
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

        **clean_stats
    )

    session.add(p)
    session.commit()
    session.refresh(p)

    _persist_pitch_arsenal(session, p, data.get('pitch_arsenal'), clean_stats)
    seed_relationships(session, p)
    grant_user_creation_trait_rolls(session, p, rolls=3)
    maybe_assign_bad_trait(session, p)
    return p.id


def _persist_pitch_arsenal(session: Session, player: Player, pitch_names: Optional[List[str]], stats: dict) -> None:
    if not player or player.position != "Pitcher":
        return

    picks = _dedupe_preserve_order([p for p in (pitch_names or []) if p in PITCH_SELECTION_POOL])
    if not picks:
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
        requests = [DecisionRequest(kind="log", message=line) for line in lines]
        requests.append(prompt)
        return DecisionResult(summary=None, requests=requests, done=False, data=self._serialize_state())

    def _serialize_state(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "state": self.state.__dict__,
        }

    # --------- step processing ---------
    def advance(self, response: Optional[str] = None) -> DecisionResult:
        # Handle response to previous prompt
        if self._awaiting:
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
                return self._step_starter_trait()
            if self.step == 3:
                return self._step_stats()
            if self.step == 4:
                return self._step_growth_style()
            if self.step == 5:
                return self._step_hometown()
            if self.step == 6:
                return self._step_school()
            if self.step == 7:
                return self._step_pitch_arsenal()
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
            return self._prompt("First Name: ")
        if phase == "last":
            self._awaiting = "name_last"
            return self._prompt("Last Name: ")
        if phase == "confirm":
            self._awaiting = "name_confirm"
            full = f"{self.state.last_name} {self.state.first_name}".strip()
            return self._log_and_prompt(
                [f"Name: {full or '--'}"],
                DecisionRequest(kind="prompt", message="Continue with this name? (y/n)", options=["y", "n"], default="n"),
            )
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
        if (value or "").lower().startswith("y"):
            self._scratch.pop("name_phase", None)
            self.step += 1
        else:
            self._scratch["name_phase"] = "first"

    # --- Step 1: position ---
    def _step_position(self) -> DecisionResult:
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
        lines = ["Select Player Position"] + [f"{idx}. {label}" for idx, label in enumerate(positions, start=1)] + ["0. Back"]
        self._awaiting = "position_pick"
        return self._log_and_prompt(
            lines,
            DecisionRequest(kind="prompt", message="Choice: ", default="0"),
        )

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
            self.step += 1

    # --- Step 2: starter trait ---
    def _step_starter_trait(self) -> DecisionResult:
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
            lines = [
                "Starter Trait Gacha",
                "One roll decides if the coaches tag you with the Starter trait.",
                "Odds: 35% chance. No rerolls.",
                "1. Roll Gacha",
                "0. Back",
            ]
            return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="Choice: ", default="0"))
        lines = [
            "Starter Trait secured." if status else "No Starter Trait. Earn it through performance.",
            "1. Continue",
            "0. Back",
        ]
        self._awaiting = "starter_ack"
        return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="Choice: ", default="1"))

    def _handle_starter_roll(self, value: str) -> None:
        if value == "0":
            self.step = max(0, self.step - 1)
            return
        if value == "1":
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
        if s.get('is_two_way') and s.get('secondary_position'):
            primary = self.state.position or 'Primary'
            lines.append(f"TWO-WAY POTENTIAL: {primary} / {s['secondary_position']}")
        lines.append("1. Accept Stats")
        lines.append("2. Reroll" + (" (LOCKED)" if self.state.rerolls_left <= 0 else ""))
        lines.append("0. Back")
        self._awaiting = "stats_choice"
        return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="Choice: ", default="1"))

    def _handle_stats_choice(self, value: str) -> None:
        if value == "0":
            self.step = max(0, self.step - 1)
            return
        if value == "1":
            self.step += 1
            return
        if value == "2":
            if self.state.rerolls_left > 0:
                self.state.rerolls_left -= 1
                self.state.stats = roll_stats(self.state.position)
            return

    # --- Step 4: growth style ---
    def _step_growth_style(self) -> DecisionResult:
        if self.state.position == "Pitcher":
            styles = ["Power Pitcher", "Technical Pitcher", "Fierce Pitcher", "Marathon Pitcher", "Balanced"]
        elif self.state.position == "Catcher":
            styles = ["Offensive Catcher", "Defensive General", "Balanced"]
        else:
            styles = ["Power Hitter", "Speedster", "Balanced"]
        lines = [f"Select Growth Style for {self.state.specific_pos}"]
        lines.extend([f"{i+1}. {s}" for i, s in enumerate(styles)])
        lines.append("0. Back")
        self._scratch["growth_styles"] = styles
        self._awaiting = "growth_pick"
        return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="Choice: ", default="1"))

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
            self.step += 1

    # --- Step 5: hometown ---
    def _step_hometown(self) -> DecisionResult:
        # simplified: pick prefecture and optional city by free text search
        prefectures = get_prefecture_catalog(self.session)
        if not prefectures:
            self.state.hometown = "Tokyo"
            self.state.prefecture_choice = "Tokyo"
            self.step += 1
            return self.advance()
        if "hometown_phase" not in self._scratch:
            self._scratch["hometown_phase"] = "pref"
        phase = self._scratch["hometown_phase"]
        if phase == "pref":
            lines = ["Select Prefecture (type name, 0 to Back)"]
            lines.extend([", ".join(prefectures[i:i+5]) for i in range(0, len(prefectures), 5)])
            self._awaiting = "hometown_pref"
            return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="Prefecture: ", default="Tokyo"))
        if phase == "city":
            pref = self.state.prefecture_choice or ""
            cities = _load_cities_for_prefecture(self.session, pref)
            names = [c['name'] for c in cities][:15]
            lines = [f"Prefecture: {pref}", "Enter city keyword or leave blank to use prefecture only."]
            if names:
                lines.append("Examples: " + ", ".join(names))
            self._awaiting = "hometown_city"
            return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="City (blank to skip): ", default=""))
        # done
        self._scratch.pop("hometown_phase", None)
        self.step += 1
        return self.advance()

    def _handle_hometown_pref(self, value: str) -> None:
        val = value.strip()
        if val == "0":
            self.step = max(0, self.step - 1)
            return
        prefectures = get_prefecture_catalog(self.session)
        matches = [p for p in prefectures if val.lower() in p.lower()] if val else prefectures
        if not matches:
            return
        pick = matches[0]
        self.state.prefecture_choice = pick
        self._scratch["hometown_phase"] = "city"

    def _handle_hometown_city(self, value: str) -> None:
        pref = self.state.prefecture_choice or ""
        city = value.strip()
        if city:
            cities = _load_cities_for_prefecture(self.session, pref)
            match = next((c for c in cities if city.lower() in c['name'].lower()), None)
            if match:
                self.state.hometown = f"{pref} — {match['name']}"
            else:
                self.state.hometown = f"{pref} — {city}"
        else:
            self.state.hometown = pref
        self._scratch.pop("hometown_phase", None)
        self.step += 1

    # --- Step 6: school ---
    def _step_school(self) -> DecisionResult:
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
        lines = [f"Offers from {pref}{' — ' + city if city else ''}:"]
        for i, t in enumerate(offers):
            lines.append(f" {i+1}. {t.name} (Rank: {t.prestige})")
        lines.append("0. Back")
        self._awaiting = "school_pick"
        return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="Select Team: ", default="1"))

    def _handle_school_pick(self, value: str) -> None:
        offers: List[School] = self._scratch.get("school_offers", [])
        if value == "0":
            self.step = max(0, self.step - 1)
            return
        if not value.isdigit():
            return
        idx = int(value) - 1
        if 0 <= idx < len(offers):
            self.state.school = offers[idx]
            acad_skill, last_score = roll_academic_profile(self.state.hometown, self.state.school)
            self.state.stats = self.state.stats or {}
            self.state.stats['academic_skill'] = acad_skill
            self.state.stats['test_score'] = last_score
            self.step += 1

    # --- Step 7: pitch arsenal ---
    def _step_pitch_arsenal(self) -> DecisionResult:
        if self.state.position != "Pitcher":
            self.state.pitch_arsenal = []
            self.step += 1
            return self.advance()
        current = ", ".join(self.state.pitch_arsenal) if self.state.pitch_arsenal else "--"
        lines = [
            "Configure Pitch Arsenal",
            f"Need {MIN_PITCHES}-{MAX_PITCHES} total pitches.",
            f"Current: {current}",
            "Enter comma-separated pitch names or leave blank for defaults.",
            "Valid options: " + ", ".join(PITCH_SELECTION_POOL),
        ]
        self._awaiting = "pitch_entry"
        return self._log_and_prompt(lines, DecisionRequest(kind="prompt", message="Pitches: ", default=", ".join(DEFAULT_PITCH_ARSENAL)))

    def _handle_pitch_entry(self, value: str) -> None:
        picks = [p.strip() for p in (value or "").split(',') if p.strip()]
        valid, message = _validate_pitch_selection(picks)
        if not valid:
            self._scratch["pitch_error"] = message
            return
        self.state.pitch_arsenal = _dedupe_preserve_order(picks)
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
        if self.state.position == "Pitcher":
            arm_slot = (self.state.stats or {}).get('arm_slot') or "Three-Quarters"
            summary_lines.append(f"Arm Slot: {arm_slot}")
            trait_txt = "Unlocked" if self.state.starter_trait else "--"
            summary_lines.append(f"Starter Trait: {trait_txt}")
            arsenal = _dedupe_preserve_order(self.state.pitch_arsenal)
            summary_lines.append(f"Pitches: {', '.join(arsenal) if arsenal else '--'}")
        summary_lines.append("1. Start Game")
        summary_lines.append("0. Back")
        self._awaiting = "final_choice"
        return self._log_and_prompt(summary_lines, DecisionRequest(kind="prompt", message="Choice: ", default="1"))

    def _handle_final_choice(self, value: str) -> None:
        if value == "0":
            self.step = max(0, self.step - 1)
            return
        if value == "1":
            player_id = commit_player_to_db(self.session, self.state.__dict__)
            self._scratch["created_player_id"] = player_id
            self.step += 1

    # --------- terminal ---------
    def is_complete(self) -> bool:
        return self.step > 8 and "created_player_id" in self._scratch

    def result(self) -> Optional[int]:
        return self._scratch.get("created_player_id")


def drive_create_player(session: Session, io: Optional[IOInterface] = None) -> Optional[int]:
    """Compatibility adapter that drives the decision engine using IOInterface."""

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
                    response = input(request.message)
        if result.done and engine.result() is not None:
            return engine.result()
        if engine.is_complete():
            return engine.result()


create_hero = drive_create_player


if __name__ == "__main__":
    from database.setup_db import get_session

    temp_session = get_session()
    try:
        create_hero(temp_session)
    finally:
        temp_session.close()
                _io_log(io, f"Pitches: {', '.join(arsenal) if arsenal else '--'}")
            _io_log(io, "─" * FRAME_WIDTH)

            _io_log(io, "1. Start Game")
            _io_log(io, "0. Back")

            sel = _io_prompt(io, "Choice: ")
            if sel == '0': step -= 1; continue
            elif sel == '1':
                player_id = commit_player_to_db(session, data)
                _io_log(io, f"{Colour.GREEN}Character Saved! Good Luck!{Colour.RESET}")
                time.sleep(2)
                return player_id

    return None


if __name__ == "__main__":
    from database.setup_db import get_session

    temp_session = get_session()
    try:
        create_hero(temp_session)
    finally:
        temp_session.close()