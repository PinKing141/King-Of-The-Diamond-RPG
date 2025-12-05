import sys
import os
import random
import time
from typing import Optional, List, Tuple, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.setup_db import School, Player, PitchRepertoire
from ui.ui_display import Colour, clear_screen
from player_roles.two_way import roll_two_way_profile
from game.academic_system import roll_academic_profile
from game.relationship_manager import seed_relationships
from game.personality import roll_player_personality
from game.player_generation import maybe_assign_bad_trait
from game.trait_logic import grant_user_creation_trait_rolls
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

FRAME_WIDTH = 84
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

_PREFECTURE_CACHE: Optional[List[str]] = None
_CITY_CACHE: Dict[str, List[str]] = {}


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


def _load_cities_for_prefecture(session: Session, prefecture: str) -> List[str]:
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
        city_names = [row[0] for row in rows if row[0]]
    except Exception as exc:
        print(f"City lookup failed for {prefecture}: {exc}")
        city_names = []

    _CITY_CACHE[prefecture] = city_names
    return city_names


def get_city_matches(session: Session, prefecture: str, search_term: str = "") -> List[str]:
    cities = _load_cities_for_prefecture(session, prefecture)
    if not cities:
        return []

    term = search_term.strip().lower()
    filtered = [c for c in cities if term in c.lower()] if term else cities
    limited = filtered[:20]
    return [f"{prefecture} — {city}" for city in limited]


def _bar(value: Optional[int], width: int = 20) -> str:
    if value is None:
        return " " * width
    pct = max(0, min(99, int(value))) / 100
    filled = int(pct * width)
    return ("█" * filled) + ("░" * (width - filled))


def _render_creation_banner(step: int, data: dict, subtitle: str) -> None:
    clear_screen()
    stage_index = min(step, TOTAL_STEPS - 1)
    stage = stage_index + 1
    print(f"{Colour.CYAN}{'═' * FRAME_WIDTH}{Colour.RESET}")
    title = f"CHARACTER CREATION  |  STEP {stage}/{TOTAL_STEPS}"
    print(title.center(FRAME_WIDTH))
    print(subtitle.center(FRAME_WIDTH))
    print(f"{Colour.CYAN}{'═' * FRAME_WIDTH}{Colour.RESET}")

    full_name = " ".join(part for part in [data['first_name'], data['last_name']] if part).strip()
    summary = [
        f"Name: {full_name or '--'}",
        f"Focus: {data.get('specific_pos') or '--'} ({data.get('position') or '--'})",
        f"Hometown: {data.get('hometown') or '--'}",
        f"School: {(data.get('school').name if data.get('school') else '--')}"
    ]
    for line in summary:
        print(line.ljust(FRAME_WIDTH))
    print("─" * FRAME_WIDTH)


def _render_stat_overview(position: str, stats: dict) -> None:
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


def _print_option(title: str) -> None:
    print(f"{Colour.GOLD}{title}{Colour.RESET}")


def _validate_pitch_selection(selection: Optional[List[str]]) -> Tuple[bool, str]:
    picks = [p for p in (selection or []) if p in PITCH_SELECTION_POOL]
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
    else:
        stats['velocity'] = 0

    return stats


# ------------------------------------------------------
# SAVE PLAYER TO DB (now includes height fields)
# ------------------------------------------------------
def commit_player_to_db(session: Session, data) -> int:
    s = data['stats']
    if data.get('position') == "Pitcher" and not data.get('pitch_arsenal'):
        data['pitch_arsenal'] = list(DEFAULT_PITCH_ARSENAL)
    valid_cols = [c.key for c in Player.__table__.columns]
    clean_stats = {k: v for k, v in s.items() if k in valid_cols}

    if 'academic_skill' not in clean_stats or 'test_score' not in clean_stats:
        academic_skill, test_score = roll_academic_profile(data.get('hometown'), data.get('school'))
        clean_stats['academic_skill'] = academic_skill
        clean_stats['test_score'] = test_score

    if data.get('starter_trait') and data.get('position') == "Pitcher":
        clean_stats['is_starter'] = True
        clean_stats['role'] = "STARTER"
    else:
        clean_stats.setdefault('is_starter', False)

    growth_tag = clean_stats.pop("growth_tag", None)
    traits = roll_player_personality(data.get('school'))
    clean_stats.setdefault('drive', traits['drive'])
    clean_stats.setdefault('loyalty', traits['loyalty'])
    clean_stats.setdefault('volatility', traits['volatility'])
    determination_seed = traits['drive'] + random.randint(-6, 6)
    clean_stats.setdefault('determination', max(30, min(95, determination_seed)))
    clean_stats.setdefault('ability_points', 0)
    clean_stats.setdefault('training_xp', '{}')

    p = Player(
        first_name=data['first_name'],
        last_name=data['last_name'],
        name=f"{data['first_name']} {data['last_name']}",
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
    if not player or not pitch_names or player.position != "Pitcher":
        return

    control = stats.get('control') or getattr(player, 'control', 50) or 50
    movement = stats.get('movement') or getattr(player, 'movement', 50) or 50

    for name in pitch_names:
        quality = max(30, min(95, int(control + random.randint(-6, 6))))
        break_level = max(30, min(95, int(movement + random.randint(-6, 6))))
        entry = PitchRepertoire(
            player_id=player.id,
            pitch_name=name,
            pitch_type=name, # Using name as type if no mapping
            quality=quality,
            break_level=break_level,
        )
        session.add(entry)
    session.commit()



# ------------------------------------------------------
# CHARACTER CREATION MENU (unchanged logic)
# ------------------------------------------------------
def create_hero(session: Session) -> Optional[int]:
    _reset_hometown_cache()
    step = 0
    data = {
        "first_name": "", "last_name": "",
        "position": None, "specific_pos": None,
        "growth_style": None,
        "stats": None, "rerolls_left": 3,
        "hometown": None,
        "prefecture_choice": None,
        "school": None,
        "pitch_arsenal": [],
        "starter_trait": None,
    }
    
    while True:
        step_title = STEP_TITLES.get(step, "Overview")
        _render_creation_banner(step, data, step_title)
        
        # STEP 0: NAME ENTRY
        if step == 0:
            _print_option("Player Identity")
            
            # --- FIX: Avoid double prompts by only showing current if set ---
            if data['first_name'] or data['last_name']:
                print(f"Current: {data['first_name']} {data['last_name']}")
            print("Enter new values or leave blank to keep current.")
            
            first = input("First Name: ").strip()
            if first:
                data['first_name'] = first
            last = input("Last Name: ").strip()
            if last:
                data['last_name'] = last
            
            if not data['first_name']:
                print("First name is required.")
                time.sleep(1)
                continue
            if not data['last_name']:
                print("Last name is required.")
                time.sleep(1)
                continue
            
            confirm = input("Continue with this name? (y/n): ").strip().lower()
            if confirm == 'y':
                step += 1
            continue

        # STEP 1: POSITION SELECTION
        elif step == 1:
            _print_option("Select Player Position")
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
            for idx, label in enumerate(positions, start=1):
                print(f" {idx}. {label}")
            print(" 0. Back")
            print(f"{Colour.GOLD}Coach's staff will decide starter vs reliever roles after creation.{Colour.RESET}")

            choice = input("Choice: ").strip()
            if choice == '0':
                step -= 1
                continue
            if not choice.isdigit():
                continue
            pick = int(choice) - 1
            if 0 <= pick < len(positions):
                specific = positions[pick]
                data['specific_pos'] = specific
                if specific == "Pitcher":
                    data['position'] = "Pitcher"
                elif specific == "Catcher":
                    data['position'] = "Catcher"
                elif specific in {"First Base", "Second Base", "Third Base", "Shortstop"}:
                    data['position'] = "Infielder"
                else:
                    data['position'] = "Outfielder"
                if data['position'] != "Pitcher":
                    data['pitch_arsenal'] = []
                    data['starter_trait'] = None
                else:
                    data['starter_trait'] = None
                step += 1
            continue

        # STEP 2: STARTER TRAIT GACHA
        elif step == 2:
            if not data.get('position'):
                print("Select a position before rolling for traits.")
                time.sleep(1)
                step -= 1
                continue
            if data['position'] != "Pitcher":
                data['starter_trait'] = None
                step += 1
                continue

            _print_option("Starter Trait Gacha")
            status = data.get('starter_trait')
            if status is None:
                print("One roll decides if the coaches tag you with the Starter trait.")
                print("Odds: 35% chance. No rerolls.")
                print("1. Roll Gacha")
                print("0. Back")
                sel = input("Choice: ").strip()
                if sel == '0':
                    step -= 1
                    continue
                if sel == '1':
                    won = random.random() < 0.35
                    data['starter_trait'] = won
                    message = "Starter trait unlocked!" if won else "No starter trait this time."
                    colour = Colour.GREEN if won else Colour.RED
                    print(f"{colour}{message}{Colour.RESET}")
                    time.sleep(1.5)
                continue

            result_txt = "Starter Trait secured. Coaches expect you to anchor games." if status else "No Starter Trait. Earn it through performance."
            print(result_txt)
            print("1. Continue")
            print("0. Back")
            sel = input("Choice: ").strip()
            if sel == '0':
                data['starter_trait'] = None
                step -= 1
                continue
            if sel == '1':
                step += 1
            continue

        # STEP 3: STATS + REROLLS (NOW BEFORE GROWTH STYLE)
        elif step == 3:
            if data['stats'] is None:
                data['stats'] = roll_stats(data['position'])
            
            s = data['stats']
            print(f"Rerolls left: {data['rerolls_left']}")
            print(f"HEIGHT: {s['height_cm']} cm")
            print(f"WEIGHT: {s['weight_kg']} kg")
            if s.get('is_two_way') and s.get('secondary_position'):
                primary = data.get('position') or 'Primary'
                print(f"{Colour.gold}TWO-WAY POTENTIAL: {primary} / {s['secondary_position']}{Colour.RESET}")

            _render_stat_overview(data['position'], s)

            print("\nOptions:")
            print("1. Accept Stats")
            if data['rerolls_left'] > 0:
                print("2. Reroll (Uses 1 attempt)")
            else:
                print("2. Reroll (LOCKED)")
            print("0. Back")

            sel = input("Choice: ")
            if sel == '0': step -= 1; continue
            elif sel == '1': step += 1; continue
            elif sel == '2':
                if data['rerolls_left'] > 0:
                    data['rerolls_left'] -= 1
                    data['stats'] = roll_stats(data['position'])
                else:
                    print("No rerolls left!")
                    time.sleep(1)

        # STEP 4: GROWTH STYLE (AFTER STATS)
        elif step == 4:
            _print_option(f"Select Growth Style for {data['specific_pos']}:")

            if data['position'] == "Pitcher":
                styles = ["Power Pitcher", "Technical Pitcher", "Fierce Pitcher", "Marathon Pitcher", "Balanced"]
            elif data['position'] == "Catcher":
                styles = ["Offensive Catcher", "Defensive General", "Balanced"]
            else:
                styles = ["Power Hitter", "Speedster", "Balanced"]

            for i, s in enumerate(styles): print(f" {i+1}. {s}")
            print(" 0. Back")

            sel = input("Choice: ")
            if sel == '0': step -= 1; continue

            try:
                idx = int(sel) - 1
                if 0 <= idx < len(styles):
                    s_name = styles[idx]
                    info = GROWTH_STYLE_INFO.get(s_name, GROWTH_STYLE_INFO['Balanced'])

                    print(f"\n{Colour.gold}>> {s_name} <<{Colour.RESET}")
                    print(f"{info['desc']}")
                    print(f"{Colour.GREEN}PROS: {info['pros']}{Colour.RESET}")
                    print(f"{Colour.RED}CONS: {info['cons']}{Colour.RESET}")

                    if input("Confirm? (y/n): ").lower() == 'y':
                        data['growth_style'] = s_name
                        step += 1
            except: pass

        # STEP 5: HOMETOWN (PREFECTURE -> CITY)
        elif step == 5:
            prefectures = get_prefecture_catalog(session)
            if not prefectures:
                print("No prefecture data found. Defaulting to Tokyo.")
                data['hometown'] = "Tokyo"
                data['prefecture_choice'] = "Tokyo"
                step += 1
                continue

            selected_pref = None
            back_to_prev = False
            while not selected_pref and not back_to_prev:
                _print_option("Select Prefecture (type to filter, 0 to Back):")
                filter_text = input("Filter: ").strip().lower()
                if filter_text == '0':
                    step -= 1
                    back_to_prev = True
                    break
                filtered = [p for p in prefectures if filter_text in p.lower()] or prefectures
                for idx, pref in enumerate(filtered, start=1):
                    print(f" {idx:>2}. {pref}")
                choice = input("Choice #: ").strip()
                if not choice.isdigit():
                    continue
                pick = int(choice)
                if 1 <= pick <= len(filtered):
                    selected_pref = filtered[pick - 1]
            if back_to_prev:
                data['prefecture_choice'] = None
                continue
            if not selected_pref:
                continue
            data['prefecture_choice'] = selected_pref

            while True:
                _print_option(f"{selected_pref}: enter city keyword (blank lists popular). 0=Back")
                city_term = input("City Search: ").strip()
                if city_term == '0':
                    selected_pref = None
                    data['prefecture_choice'] = None
                    break
                matches = get_city_matches(session, selected_pref, city_term)
                if not matches:
                    print("No cities found. Use prefecture only?")
                    if input("Use prefecture only (y/n): ").lower() == 'y':
                        data['hometown'] = selected_pref
                        step += 1
                        break
                    continue
                print("\nSelect City:")
                print(" 0. Use prefecture only")
                for i, m in enumerate(matches, start=1):
                    print(f" {i}. {m}")
                choice = input("Choice: ").strip()
                if not choice.isdigit():
                    continue
                pick = int(choice)
                if pick == 0:
                    data['hometown'] = selected_pref
                    step += 1
                    break
                if 1 <= pick <= len(matches):
                    data['hometown'] = matches[pick - 1]
                    step += 1
                    break
            if not selected_pref:
                continue

        # STEP 6: SCHOOL SELECTION
        elif step == 6:
            hometown = data.get('hometown') or ''
            pref = data.get('prefecture_choice')
            if not pref and hometown:
                pref = hometown.split('—')[0].strip()
            pref = pref or "Tokyo"

            city = None
            if '—' in hometown:
                city = hometown.split('—', 1)[1].strip()

            base_query = session.query(School).filter(School.prefecture == pref)
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
                offers = session.query(School).order_by(func.random()).limit(5).all()

            location_label = f"{pref} — {city}" if city else pref
            _print_option(f"Offers from {location_label}:")
            for i, t in enumerate(offers):
                print(f" {i+1}. {t.name} (Rank: {t.prestige})")
            print(" 0. Back")
            
            sel = input("Select Team: ")
            if sel == '0': step -= 1; continue
            
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(offers):
                    data['school'] = offers[idx]
                    acad_skill, last_score = roll_academic_profile(data.get('hometown'), data['school'])
                    data.setdefault('stats', {})
                    data['stats']['academic_skill'] = acad_skill
                    data['stats']['test_score'] = last_score
                    step += 1
            except: pass

        # STEP 7: PITCH SELECTION (PITCHERS ONLY)
        elif step == 7:
            if data['position'] != "Pitcher":
                data['pitch_arsenal'] = []
                step += 1
                continue

            selected = list(data['pitch_arsenal'] or DEFAULT_PITCH_ARSENAL)
            while True:
                _print_option("Configure Pitch Arsenal")
                print(f"Need {MIN_PITCHES}-{MAX_PITCHES} total pitches. Mix and match however you like.")
                current_display = ", ".join(selected) if selected else "--"
                print(f"Selected [{len(selected)}/{MAX_PITCHES}]: {current_display}")
                print("Choices: toggle #, D=Done, R=Reset defaults, C=Clear, 0=Back")
                for idx, pitch in enumerate(PITCH_SELECTION_POOL, start=1):
                    marker = "*" if pitch in selected else " "
                    fb_tag = " (FB)" if pitch in FASTBALL_PITCHES else ""
                    print(f" {idx:>2}. [{marker}] {pitch}{fb_tag}")

                sel = input("Command: ").strip().lower()
                if sel in {'0', 'b'}:
                    data['pitch_arsenal'] = selected
                    step -= 1
                    break
                if sel in {'d', 'done'}:
                    valid, message = _validate_pitch_selection(selected)
                    if valid:
                        data['pitch_arsenal'] = selected
                        step += 1
                        break
                    print(message)
                    time.sleep(1)
                    continue
                if sel in {'c', 'clear'}:
                    selected = []
                    continue
                if sel in {'r', 'reset'}:
                    selected = list(DEFAULT_PITCH_ARSENAL)
                    continue
                if sel.isdigit():
                    idx = int(sel) - 1
                    if 0 <= idx < len(PITCH_SELECTION_POOL):
                        pitch_name = PITCH_SELECTION_POOL[idx]
                        if pitch_name in selected:
                            selected.remove(pitch_name)
                        else:
                            if len(selected) >= MAX_PITCHES:
                                print(f"Remove a pitch before adding a new one (max {MAX_PITCHES}).")
                                time.sleep(1)
                                continue
                            selected.append(pitch_name)
                    continue
                print("Unknown command.")
                time.sleep(1)
                continue
            continue

        # STEP 8: FINAL CONFIRMATION
        elif step == 8:
            print(f"Name:   {data['first_name']} {data['last_name']}")
            print(f"Role:   {data['specific_pos']}")
            print(f"Style:  {data['growth_style']}")
            print(f"Hometown: {data['hometown']}")
            school_name = data['school'].name if data.get('school') else '--'
            print(f"School: {Colour.gold}{school_name}{Colour.RESET}")
            acad_skill = data['stats'].get('academic_skill', '??')
            last_score = data['stats'].get('test_score', '??')
            print(f"Academics: Skill {acad_skill} / Latest Test {last_score}")
            if data['position'] == "Pitcher":
                trait_txt = "Unlocked" if data.get('starter_trait') else "--"
                print(f"Starter Trait: {trait_txt}")
                pitch_summary = ", ".join(data.get('pitch_arsenal') or DEFAULT_PITCH_ARSENAL)
                print(f"Pitches: {pitch_summary}")
            print("─" * FRAME_WIDTH)
            
            print("1. Start Game")
            print("0. Back")
            
            sel = input("Choice: ")
            if sel == '0': step -= 1; continue
            elif sel == '1':
                player_id = commit_player_to_db(session, data)
                print(f"{Colour.GREEN}Character Saved! Good Luck!{Colour.RESET}")
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