import sys
import os
import random
import time
import sqlite3
from typing import Optional

from sqlalchemy.orm import Session

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.setup_db import School, Player
from config import CITIES_DB_PATH
from ui.ui_display import Colour, clear_screen
from player_roles.two_way import roll_two_way_profile
from game.academic_system import roll_academic_profile
from game.relationship_manager import seed_relationships
from game.personality import roll_player_personality
from game.player_generation import maybe_assign_bad_trait
from game.trait_logic import grant_user_creation_trait_rolls

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
#  CITY SEARCH
# ------------------------------------------------------
def get_city_matches(search_term):
    matches = []
    if not os.path.exists(CITIES_DB_PATH): return []

    try:
        conn = sqlite3.connect(CITIES_DB_PATH)
        c = conn.cursor()

        # Determine correct table
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jpcities'")
        if c.fetchone():
            tbl = "jpcities"
        else:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Cities'")
            tbl = "Cities" if c.fetchone() else "cities"

        query = f"""
            SELECT admin_name, city 
            FROM {tbl} 
            WHERE lower(city) LIKE ? 
               OR lower(city_ascii) LIKE ? 
               OR lower(admin_name) LIKE ?
            ORDER BY admin_name, city
            LIMIT 20
        """

        term = f"%{search_term.lower()}%"
        c.execute(query, (term, term, term))
        matches = [f"{row[0]} — {row[1]}" for row in c.fetchall()]
        conn.close()

    except Exception as e:
        print(f"City DB Error: {e}")

    return matches



# ------------------------------------------------------
# SAVE PLAYER TO DB (now includes height fields)
# ------------------------------------------------------
def commit_player_to_db(session: Session, data) -> int:
    s = data['stats']
    valid_cols = [c.key for c in Player.__table__.columns]
    clean_stats = {k: v for k, v in s.items() if k in valid_cols}

    if 'academic_skill' not in clean_stats or 'test_score' not in clean_stats:
        academic_skill, test_score = roll_academic_profile(data.get('hometown'), data.get('school'))
        clean_stats['academic_skill'] = academic_skill
        clean_stats['test_score'] = test_score

    growth_tag = clean_stats.pop("growth_tag", None)
    traits = roll_player_personality(data.get('school'))
    clean_stats.setdefault('drive', traits['drive'])
    clean_stats.setdefault('loyalty', traits['loyalty'])
    clean_stats.setdefault('volatility', traits['volatility'])

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
    seed_relationships(session, p)
    grant_user_creation_trait_rolls(session, p, rolls=3)
    maybe_assign_bad_trait(session, p)
    return p.id



# ------------------------------------------------------
# CHARACTER CREATION MENU (unchanged logic)
# ------------------------------------------------------
def create_hero(session: Session) -> Optional[int]:
    step = 0
    data = {
        "first_name": "Taro", "last_name": "Yamada",
        "position": None, "specific_pos": None,
        "growth_style": None,
        "stats": None, "rerolls_left": 3,
        "hometown": None,
        "school": None
    }
    
    while True:
        clear_screen()
        print(f"{Colour.HEADER}--- CHARACTER CREATION (Step {step}/6) ---{Colour.RESET}")
        
        # STEP 0: NAME
        if step == 0:
            print("Enter Name (or press Enter for default):")
            f = input(f"First Name [{data['first_name']}]: ").strip()
            l = input(f"Last Name  [{data['last_name']}]:  ").strip()
            if f: data['first_name'] = f.capitalize()
            if l: data['last_name'] = l.capitalize()
            step += 1
            
        # STEP 1: POSITION
        elif step == 1:
            print(f"{Colour.CYAN}Select Position:{Colour.RESET}")
            opts = ["Pitcher", "Catcher", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
            for i, p in enumerate(opts): print(f" {i+1}. {p}")
            print(" 0. Back")
            
            sel = input("Choice: ")
            if sel == '0': step -= 1; continue
            
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(opts):
                    data['specific_pos'] = opts[idx]
                    if opts[idx] == "Pitcher": data['position'] = "Pitcher"
                    elif opts[idx] == "Catcher": data['position'] = "Catcher"
                    elif opts[idx] in ["1B", "2B", "3B", "SS"]: data['position'] = "Infielder"
                    else: data['position'] = "Outfielder"
                    step += 1
            except: pass

        # STEP 2: STATS + REROLLS (NOW BEFORE GROWTH STYLE)
        elif step == 2:
            if data['stats'] is None:
                data['stats'] = roll_stats(data['position'])
            
            s = data['stats']
            print(f"\n{Colour.HEADER}--- BASE STATS (Rerolls left: {data['rerolls_left']}) ---{Colour.RESET}")

            print(f"HEIGHT: {s['height_cm']} cm")
            print(f"WEIGHT: {s['weight_kg']} kg")
            if s.get('is_two_way') and s.get('secondary_position'):
                print(f"{Colour.gold}TWO-WAY POTENTIAL: {s['position']} / {s['secondary_position']}{Colour.RESET}")

            if data['position'] == "Pitcher":
                print(f"VEL: {s['velocity']} km/h   STA: {s['stamina']}   CTRL: {s['control']}   MOV: {s['movement']}")
            else:
                print(f"CON: {s['contact']}  PWR: {s['power']}  SPD: {s['speed']}  FLD: {s['fielding']}  THR: {s['throwing']}")

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

        # STEP 3: GROWTH STYLE (AFTER STATS)
        elif step == 3:
            print(f"{Colour.CYAN}Select Growth Style for {data['specific_pos']}:{Colour.RESET}")

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

        # STEP 4: HOMETOWN
        elif step == 4:
            print(f"{Colour.CYAN}Enter Hometown Search (Prefecture or City):{Colour.RESET}")
            print("0. Back")
            term = input("Search: ").strip()
            
            if term == '0': step -= 1; continue
            
            matches = get_city_matches(term)
            if not matches:
                print("No matches found. Using 'Tokyo' as default?")
                if input("Confirm? (y/n): ").lower() == 'y':
                    data['hometown'] = "Tokyo"
                    step += 1
            else:
                print("\nSelect City:")
                for i, m in enumerate(matches): print(f" {i+1}. {m}")
                try:
                    idx = int(input("Choice: ")) - 1
                    if 0 <= idx < len(matches):
                        data['hometown'] = matches[idx] 
                        step += 1
                except: pass

        # STEP 5: SCHOOL SELECTION
        elif step == 5:
            pref = data['hometown'].split('—')[0].strip() if '—' in data['hometown'] else "Tokyo"
            
            offers = session.query(School).filter(School.prefecture == pref).limit(5).all()
            if not offers:
                offers = session.query(School).limit(5).all()
            
            print(f"\n{Colour.CYAN}Offers from {pref}:{Colour.RESET}")
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

        # STEP 6: FINAL CONFIRMATION
        elif step == 6:
            print(f"\n{Colour.HEADER}=== CONFIRM PROFILE ==={Colour.RESET}")
            print(f"Name:   {data['first_name']} {data['last_name']}")
            print(f"Role:   {data['specific_pos']}")
            print(f"Style:  {data['growth_style']}")
            print(f"Hometown: {data['hometown']}")
            print(f"School: {Colour.gold}{data['school'].name}{Colour.RESET}")
            acad_skill = data['stats'].get('academic_skill', '??')
            last_score = data['stats'].get('test_score', '??')
            print(f"Academics: Skill {acad_skill} / Latest Test {last_score}")
            print("=======================")
            
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