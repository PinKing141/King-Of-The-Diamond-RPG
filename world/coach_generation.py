import random
import sqlite3
import os
import pykakasi
import sys

# Add root to path to find setup_db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.setup_db import Coach
from config import NAME_DB_PATH
from game.personality import roll_coach_personality

# Initialize converter
kks = pykakasi.kakasi()

def generate_coach_for_school(school):
    """
    Generates a Coach entity tailored to the School's philosophy.
    """
    # 1. Base Traits
    tradition = random.random()
    logic = random.random()
    temper = random.random()
    ambition = random.random()

    # Adjust base traits based on School Philosophy
    style = getattr(school, 'training_style', 'Hybrid')

    if style == "Spirit":
        tradition = min(1.0, tradition + 0.3)
        logic = max(0.0, logic - 0.2)
    elif style == "Modern":
        tradition = max(0.0, tradition - 0.3)
        logic = min(1.0, logic + 0.3)
    elif style == "Technical":
        logic = min(1.0, logic + 0.2)
        temper = max(0.0, temper - 0.2)
    
    # 2. Derive AI Weights
    base_seniority = getattr(school, 'seniority_weight', 0.5)
    derived_seniority = (base_seniority * 0.7) + (tradition * 0.3)
    
    base_stats = getattr(school, 'stats_weight', 0.5)
    derived_stats = (base_stats * 0.6) + (logic * 0.4)
    
    base_trust = getattr(school, 'trust_weight', 0.5)
    derived_trust = (base_trust * 0.5) + (tradition * 0.3) + ((1.0 - logic) * 0.2)
    
    derived_fatigue_penalty = 0.5 + (logic * 0.4) - (tradition * 0.2) - (ambition * 0.2)
    derived_fatigue_penalty = max(0.1, min(1.0, derived_fatigue_penalty))

    # 3. Create Coach Object
    coach_name_str = generate_coach_name_from_db()

    traits = roll_coach_personality(school)

    new_coach = Coach(
        school_id=school.id,
        name=coach_name_str,
        tradition=round(tradition, 2),
        logic=round(logic, 2),
        temper=round(temper, 2),
        ambition=round(ambition, 2),
        seniority_weight=round(derived_seniority, 2),
        trust_weight=round(derived_trust, 2),
        stats_weight=round(derived_stats, 2),
        fatigue_penalty_weight=round(derived_fatigue_penalty, 2),
        drive=traits['drive'],
        loyalty=traits['loyalty'],
        volatility=traits['volatility'],
    )
    
    return new_coach

def generate_coach_name_from_db():
    """
    Pulls a random Japanese Name from names.sqlite.
    """
    if not os.path.exists(NAME_DB_PATH):
        return f"Coach {generate_fallback_name()}"

    try:
        conn = sqlite3.connect(NAME_DB_PATH)
        cursor = conn.cursor()
        
        # SMART CHECK: Look for 'last_names' first, then fallback to 'names'
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='last_names'")
        if cursor.fetchone():
            cursor.execute("SELECT reading FROM last_names ORDER BY RANDOM() LIMIT 1")
        else:
            cursor.execute("SELECT kanji FROM names ORDER BY RANDOM() LIMIT 1")
            
        result = cursor.fetchone()
        conn.close()
        
        if result:
            name_text = result[0]
            # Convert to Romaji
            converted = kks.convert(name_text)
            name_romaji = "".join([item['hepburn'] for item in converted]).capitalize()
            return f"Coach {name_romaji}"
        else:
            return f"Coach {generate_fallback_name()}"
            
    except Exception:
        # Silently fail to fallback to speed up loop if DB is broken
        return f"Coach {generate_fallback_name()}"

def generate_fallback_name():
    surnames = ["Tanaka", "Yamamoto", "Saito", "Kobayashi", "Nakamura", "Kato", "Yoshida", "Yamada", "Sasaki", "Matsumoto"]
    return random.choice(surnames)