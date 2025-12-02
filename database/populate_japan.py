import random
import sys
import os
import sqlite3
import pykakasi 
import traceback

# Fix Imports for subfolder location
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NAME_DB_PATH, CITIES_DB_PATH
from match_engine.pitch_definitions import PITCH_TYPES
from database.setup_db import (
    School,
    Player,
    PitchRepertoire,
    create_database,
    Coach,
    ScoutingData,
    session_scope,
)
from world.school_philosophy import PHILOSOPHY_MATRIX
from game.archetypes import assign_player_archetype
from world.coach_generation import generate_coach_for_school
from player_roles.two_way import roll_two_way_profile


ARM_SLOT_DISTRIBUTION = [
    ("Overhand", 0.16),
    ("High Three-Quarters", 0.2),
    ("Three-Quarters", 0.22),
    ("Low Three-Quarters", 0.16),
    ("Sidearm", 0.12),
    ("Low Sidearm", 0.08),
    ("Submarine", 0.06),
]


def roll_arm_slot(focus_label: str) -> str:
    focus_label = (focus_label or "balanced").lower()
    pool = list(ARM_SLOT_DISTRIBUTION)

    def _boost(targets, delta):
        for idx, (slot, weight) in enumerate(pool):
            if slot in targets:
                pool[idx] = (slot, weight + delta)

    if focus_label in {"pitching", "technical"}:
        _boost({"Overhand", "High Three-Quarters"}, 0.03)
    if focus_label in {"power", "guts"}:
        _boost({"Low Three-Quarters", "Sidearm", "Low Sidearm"}, 0.02)
    if focus_label in {"speed", "gamblers"}:
        _boost({"Sidearm", "Submarine"}, 0.02)

    total = sum(weight for _, weight in pool)
    roll = random.random() * total
    running = 0.0
    for slot, weight in pool:
        running += weight
        if roll <= running:
            return slot
    return "Three-Quarters"
from game.personality import roll_player_personality
from game.player_generation import seed_negative_traits
from game.trait_logic import seed_initial_traits

# Initialize DB
create_database()

# --- CONFIGURATION ---
SCALE_FACTOR = 1.0 

# --- PATH CONFIGURATION ---
def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_path()

# --- PREFECTURE DATA ---
prefecture_counts = {
    "Hokkaido": 200, "Aomori": 60, "Iwate": 65, "Miyagi": 70, "Akita": 45, "Yamagata": 45, "Fukushima": 75,
    "Ibaraki": 95, "Tochigi": 60, "Gunma": 65, "Saitama": 155, "Chiba": 165,
    "Tokyo": 260, "Kanagawa": 180, "Yamanashi": 35,
    "Niigata": 80, "Toyama": 45, "Ishikawa": 45, "Fukui": 30, "Nagano": 80,
    "Gifu": 65, "Shizuoka": 110, "Aichi": 180,
    "Mie": 60, "Shiga": 50, "Kyoto": 75, "Osaka": 175, "Hyogo": 160, "Nara": 40, "Wakayama": 39,
    "Tottori": 24, "Shimane": 39, "Okayama": 60, "Hiroshima": 90, "Yamaguchi": 60,
    "Tokushima": 30, "Kagawa": 38, "Ehime": 58, "Kochi": 28,
    "Fukuoka": 135, "Saga": 40, "Nagasaki": 55, "Kumamoto": 60, "Oita": 45, "Miyazaki": 48, 
    "Kagoshima": 70, "Okinawa": 60
}

# --- DATABASE CONNECTIONS ---
kks = pykakasi.kakasi()

try:
    name_db_conn = sqlite3.connect(NAME_DB_PATH) if os.path.exists(NAME_DB_PATH) else None
    name_db_cursor = name_db_conn.cursor() if name_db_conn else None
except: name_db_conn = None

try:
    cities_db_conn = sqlite3.connect(CITIES_DB_PATH) if os.path.exists(CITIES_DB_PATH) else None
    cities_db_cursor = cities_db_conn.cursor() if cities_db_conn else None
except: cities_db_conn = None

# --- HELPERS ---

def get_random_english_name(gender='M'):
    if not name_db_conn:
        return "Yamada", "Taro"

    try:
        # SURNAME
        try:
            name_db_cursor.execute("SELECT reading FROM last_names ORDER BY RANDOM() LIMIT 1")
        except sqlite3.OperationalError:
            name_db_cursor.execute("SELECT kanji FROM names ORDER BY RANDOM() LIMIT 1")
            
        last_reading = name_db_cursor.fetchone()[0]

        # FIRST NAME
        try:
            sex_values = ["M", "m", "Male", "male", "MALE", "boy", "Boy", "BOY"]
            placeholders = ",".join("?" * len(sex_values))
            name_db_cursor.execute(
                f"SELECT reading FROM first_names WHERE sex IN ({placeholders}) ORDER BY RANDOM() LIMIT 1",
                sex_values
            )
        except sqlite3.OperationalError:
             return "Yamada", "Taro"

        row = name_db_cursor.fetchone()
        first_reading = row[0] if row else "太郎"

        # Convert readings to romaji
        l_romaji = "".join([i["hepburn"] for i in kks.convert(last_reading)]).capitalize()
        f_romaji = "".join([i["hepburn"] for i in kks.convert(first_reading)]).capitalize()

        return l_romaji, f_romaji

    except Exception:
        return "Yamada", "Taro"

def get_random_city(prefecture):
    if not cities_db_conn:
        return prefecture

    try:
        # Try exact match first
        cities_db_cursor.execute("""
            SELECT city_ascii FROM jpcities 
            WHERE admin_name = ? COLLATE NOCASE
            ORDER BY RANDOM() LIMIT 1
        """, (prefecture,))
        row = cities_db_cursor.fetchone()
        if row and row[0]: return row[0]

        # Try loose match
        cities_db_cursor.execute("""
            SELECT city_ascii FROM jpcities 
            WHERE admin_name LIKE ? 
            ORDER BY RANDOM() LIMIT 1
        """, (f"%{prefecture}%",))
        row = cities_db_cursor.fetchone()
        if row and row[0]: return row[0]

        return prefecture
    except Exception:
        return prefecture

def generate_stats(position, specific_pos, focus):
    # Generates raw stats dictionary
    stats = {}

    def _clamp(val, low=10, high=99):
        return max(low, min(high, int(val)))

    focus_label = (focus or "Balanced").lower()

    def get_val(bonus=0, tag=None):
        # Apply focus bonuses
        if focus_label == "power" and tag == "power":
            bonus += 10
        if focus_label == "speed" and tag == "speed":
            bonus += 10
        if focus_label == "defense" and tag in {"fielding", "throwing"}:
            bonus += 10
        if focus_label == "pitching" and position == "Pitcher" and tag in {"control", "movement", "stamina"}:
            bonus += 5
        if focus_label == "stamina" and tag == "stamina":
            bonus += 15
        if focus_label == "technical" and tag in {"control", "contact"}:
            bonus += 10

        # Base range 30-50 + bonus, clamped 10-99
        return _clamp(random.randint(30 + bonus, 50 + bonus))

    # Potential
    roll = random.random()
    if roll < 0.01: stats['growth_tag'] = "Limitless"
    elif roll < 0.16: stats['growth_tag'] = "Supernova"
    elif roll < 0.36: stats['growth_tag'] = "Grinder"
    else: stats['growth_tag'] = "Normal"

    pot_roll = random.random()
    if stats['growth_tag'] == "Limitless": stats['potential_grade'] = "S"
    elif pot_roll < 0.10: stats['potential_grade'] = "S"
    elif pot_roll < 0.30: stats['potential_grade'] = "A"
    elif pot_roll < 0.60: stats['potential_grade'] = "B"
    else: stats['potential_grade'] = "C"

    stats['fatigue'] = 0
    stats['overall'] = 40

    # Physical profile
    base_h = 175
    base_w = 72
    if position == "Pitcher":
        base_h = 178
        base_w = 75
    elif specific_pos in ("1B", "3B"):
        base_h = 180
        base_w = 80

    stats['height_cm'] = int(random.normalvariate(base_h, 5))
    stats['weight_kg'] = int(random.normalvariate(base_w, 8))
    stats['height_potential'] = stats['height_cm'] + random.randint(5, 20)
    
    two_way, secondary = roll_two_way_profile(position, rng=random)
    stats['stamina'] = get_val(tag="stamina")
    
    # Pitching vs Fielding
    if position == "Pitcher":
        stats['control'] = get_val(10, tag="control")
        stats['velocity'] = int(random.normalvariate(130 + (5 if focus_label == "pitching" else 0), 5))
        stats['breaking_ball'] = get_val(5, tag="movement")
        # Map to V2 Schema 'movement'
        stats['movement'] = stats['breaking_ball']
        stats['arm_slot'] = roll_arm_slot(focus_label)

        # Batting stats for pitcher (weak)
        stats['power'] = get_val(-15, tag="power")
        stats['contact'] = get_val(-15, tag="contact")
        stats['fielding'] = get_val(10, tag="fielding")
        stats['speed'] = get_val(-5, tag="speed")
    else:
        stats['velocity'] = 0
        stats['control'] = 10
        stats['movement'] = 0
        stats['arm_slot'] = "Three-Quarters"

        stats['power'] = get_val(tag="power")
        stats['contact'] = get_val(tag="contact")
        stats['fielding'] = get_val(tag="fielding")
        stats['speed'] = get_val(tag="speed")

        # Specific pos tweaks
        if specific_pos == "C":
            stats['fielding'] += 15
            stats['speed'] -= 10
        elif specific_pos == "SS":
            stats['fielding'] += 10
            stats['speed'] += 5
        elif specific_pos == "1B":
            stats['power'] += 10

    # Clamp core ratings after positional tweaks
    for attr in ("power", "contact", "speed", "fielding", "stamina", "control", "movement"):
        if attr in stats:
            stats[attr] = _clamp(stats[attr])

    # Arm strength / throwing
    if position == "Pitcher":
        stats['throwing'] = _clamp(random.randint(60, 90))
    else:
        stats['throwing'] = get_val(tag="throwing")
        if specific_pos == "C":
            stats['throwing'] += 10
        elif specific_pos in {"RF", "CF", "LF"}:
            stats['throwing'] += 8
        elif specific_pos in {"SS", "3B"}:
            stats['throwing'] += 5
        stats['throwing'] = _clamp(stats['throwing'])

    # Mental/discipline/clutch & command ratings (were previously defaults)
    mental = random.randint(35, 70)
    discipline = random.randint(32, 72)
    clutch = random.randint(32, 78)
    command = random.randint(30, 60)

    if focus_label in {"technical", "balanced"}:
        discipline += 5
    if focus_label in {"guts", "power", "gamblers"}:
        clutch += 6
    if focus_label in {"pitching", "defense"}:
        mental += 4

    if specific_pos == "C":
        mental += 6
        discipline += 5
        command += 15

    if position == "Pitcher":
        command = stats['control'] + random.randint(-5, 7)

    stats['mental'] = _clamp(mental)
    stats['discipline'] = _clamp(discipline)
    stats['clutch'] = _clamp(clutch)
    stats['command'] = _clamp(command)

    stats['is_two_way'] = two_way
    stats['secondary_position'] = secondary if secondary else None

    return stats

def generate_pitch_arsenal(player_obj, style_focus, arm_slot="Three-Quarters"):
    # Generate PitchRepertoire objects
    arsenal = []
    
    # Fastball
    fb_choice = "4-Seam Fastball"
    side_slots = {"Sidearm", "Low Sidearm", "Submarine"}
    if arm_slot in side_slots or style_focus == "Speed":
        fb_choice = random.choice(["2-Seam Fastball", "Shuuto", "Sinker", "Turbo Sinker"])
        
    fb = PitchRepertoire(
        pitch_name=fb_choice,
        quality=player_obj.control + random.randint(-5, 10),
        break_level=player_obj.movement + random.randint(-10, 5) # using movement stat
    )
    arsenal.append(fb)
    
    # Secondary Pitches
    available = [k for k in PITCH_TYPES.keys() if k != fb_choice]
    num_pitches = random.choices([2, 3, 4], weights=[40, 40, 20])[0]
    
    chosen = random.sample(available, k=min(num_pitches, len(available)))
    
    for p_name in chosen:
        pitch = PitchRepertoire(
            pitch_name=p_name,
            quality=player_obj.movement + random.randint(-10, 10),
            break_level=player_obj.movement + random.randint(-5, 15)
        )
        arsenal.append(pitch)
        
    return arsenal

used_school_names = set()
school_types = ["High School", "Academy", "Tech", "Commercial", "Gakuen"]
directions = ["East", "West", "North", "South", "Central"]

def generate_school_name(prefecture, city):
    """
    Generates unique school names. Includes fail-safe counter to prevent infinite loops.
    """
    attempts = 0
    while True:
        attempts += 1
        pattern = random.randint(1, 4)
        
        # If we are stuck, fallback to appending a number
        suffix = ""
        if attempts > 20:
            suffix = f" No.{random.randint(1, 999)}"
        
        if pattern == 1: name = f"{city} {random.choice(school_types)}{suffix}"
        elif pattern == 2: name = f"{prefecture} {random.choice(directions)} {random.choice(school_types)}{suffix}"
        elif pattern == 3: name = f"{city} {random.choice(directions)} {random.choice(school_types)}{suffix}"
        else: name = f"{prefecture} {random.choice(school_types)}{suffix}"
        
        if name not in used_school_names:
            used_school_names.add(name)
            return name

def populate_world():
    with session_scope() as session:
        print("--- SYSTEM: WIPING OLD DATA ---")
        try:
            session.query(PitchRepertoire).delete()
            session.query(Player).delete()
            session.query(ScoutingData).delete() # New table
            session.query(School).delete()
            session.query(Coach).delete()
            session.commit()
        except Exception as e:
            print(f"Error wiping data: {e}")
            session.rollback()

        print(f"--- SYSTEM: GENERATING JAPAN (Scale: {SCALE_FACTOR}) ---")
        total_schools = 0
        archetype_keys = list(PHILOSOPHY_MATRIX.keys())
        weights = [PHILOSOPHY_MATRIX[k].get('weight', 1) for k in archetype_keys]

        for pref, count in prefecture_counts.items():
            print(f"Processing: {pref}...", end=" ")
            num_schools = max(6, int(count * SCALE_FACTOR))
            
            # Districts logic (Used for count, but not stored in DB)
            districts = [pref]
            if pref in ["Tokyo", "Hokkaido"]:
                num_schools = int(num_schools / 2)
                if pref == "Tokyo": districts = ["East Tokyo", "West Tokyo"]
                else: districts = ["North Hokkaido", "South Hokkaido"]

            schools_in_pref = 0
            for current_district in districts:
                for _ in range(num_schools):
                    try:
                        phil_name = random.choices(archetype_keys, weights=weights, k=1)[0]
                        data = PHILOSOPHY_MATRIX[phil_name]
                        
                        city = get_random_city(pref)
                        s_name = generate_school_name(pref, city)
                        
                        # REVAMPED BUDGET: Multiplier for realism (e.g. Budget 100 -> 10,000,000 Yen)
                        # Base is roughly 1-5 million yen for equipment/travel
                        # Rich schools get 20-50m
                        base_budget_yen = data.get('budget', 50000) * 100 
                        # Add variance
                        final_budget = int(base_budget_yen * random.uniform(0.8, 1.2))
                        
                        school = School(
                            name=s_name,
                            prefecture=pref,
                            prestige=random.randint(20, 80),
                            budget=final_budget,
                            philosophy=phil_name,
                            focus=data.get('focus', 'Balanced'),
                            training_style=data.get('training_style', 'Modern')
                        )
                        session.add(school)
                        session.flush() # Get ID
                        schools_in_pref += 1
                        total_schools += 1
                        
                        # Generate Coach (V2)
                        coach = generate_coach_for_school(school)
                        session.add(coach)

                        # Generate Players
                        roster_players = []
                        
                        positions_needed = [
                            "Pitcher", "Pitcher", "Pitcher", "Pitcher",
                            "Catcher", "Catcher",
                            "1B", "2B", "3B", "SS",
                            "LF", "CF", "RF",
                            "Infielder", "Outfielder", "Infielder", "Outfielder", "Utility"
                        ]
                        
                        for spec_pos in positions_needed:
                            broad_pos = spec_pos
                            if spec_pos in ["1B", "2B", "3B", "SS", "Utility"]: broad_pos = "Infielder"
                            if spec_pos in ["LF", "CF", "RF"]: broad_pos = "Outfielder"
                            
                            stats = generate_stats(broad_pos, spec_pos, data.get('focus', 'Balanced'))
                            l_name, f_name = get_random_english_name('M')
                            
                            # SAFETY FILTER: Only pass stats that exist as columns
                            valid_cols = {c.key for c in Player.__table__.columns}
                            
                            p_data = {
                                "school_id": school.id,
                                "name": f"{l_name} {f_name}",
                                "first_name": f_name, 
                                "last_name": l_name,
                                "year": random.choices([1, 2, 3], weights=[30, 40, 30])[0],
                                "position": broad_pos,
                                "role": "BENCH",
                                **{k: v for k, v in stats.items() if k in valid_cols}
                            }
                            traits = roll_player_personality(school)
                            p_data['drive'] = traits['drive']
                            p_data['loyalty'] = traits['loyalty']
                            p_data['volatility'] = traits['volatility']
                            
                            player = Player(**p_data)
                            assign_player_archetype(player, school, position=spec_pos)
                            
                            # Arsenal Generation (Pitchers only)
                            class PseudoPlayer:
                                def __init__(self, s):
                                    self.control = s.get('control', 50)
                                    self.movement = s.get('movement', 50)
                            
                            if broad_pos == "Pitcher":
                                arsenal = generate_pitch_arsenal(PseudoPlayer(stats), data.get('focus'), "Overhand")
                                player.pitch_repertoire = arsenal
                            
                            roster_players.append(player)
                        
                        # Assign Roles
                        pitchers = [p for p in roster_players if p.position == "Pitcher"]
                        fielders = [p for p in roster_players if p.position != "Pitcher"]
                        
                        pitchers.sort(key=lambda x: x.velocity + x.control, reverse=True)
                        fielders.sort(key=lambda x: x.contact + x.power + x.fielding, reverse=True)
                        
                        if pitchers:
                            pitchers[0].jersey_number = 1
                            pitchers[0].role = "ACE"
                            pitchers[0].is_starter = True
                            
                        used_nums = {1}
                        for i, f in enumerate(fielders[:8]):
                            num = i + 2
                            f.jersey_number = num
                            f.is_starter = True
                            f.role = "STARTER"
                            used_nums.add(num)
                            
                        bench = pitchers[1:] + fielders[8:]
                        next_num = 10
                        for b in bench:
                            b.jersey_number = next_num
                            b.role = "BENCH"
                            if b.position == "Pitcher": b.role = "RELIEVER"
                            next_num += 1
                        
                        session.add_all(roster_players)
                        session.flush()
                        seed_initial_traits(session, roster_players)
                        seed_negative_traits(session, roster_players)
                        
                        # Visual progress
                        if schools_in_pref % 10 == 0:
                            print(".", end="", flush=True)
                    
                    except Exception as e:
                        if os.getenv("POPULATE_DEBUG"):
                            import traceback
                            traceback.print_exc()
                        continue

            session.commit()
            print(f" Done. ({schools_in_pref} Schools)")

    if name_db_conn: name_db_conn.close()
    if cities_db_conn: cities_db_conn.close()
    
    print("--- SYSTEM: DATABASE POPULATION COMPLETE ---")

if __name__ == "__main__":
    populate_world()