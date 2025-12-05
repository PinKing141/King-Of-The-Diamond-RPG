import random
import json
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

ARCHETYPE_BY_STYLE = {
    "spirit": "MOTIVATOR",
    "modern": "INNOVATOR",
    "technical": "SCIENTIST",
    "hybrid": "BALANCED",
    "traditional": "TRADITIONALIST",
}

FOCUS_ARCHETYPE_RULES = [
    ({"pitching", "battery", "ace"}, "TALENT_ENGINEER"),
    ({"power", "core"}, "SLUGGER_GURU"),
    ({"speed", "stamina", "guts"}, "TACTICIAN"),
    ({"balanced", "mental"}, "MENTOR"),
]

DEFAULT_COACH_ARCHETYPE = "TRADITIONALIST"


def _decode_scouting_network(payload):
    if not payload:
        return {}
    if isinstance(payload, dict):
        return payload
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return {}


def _infer_coach_archetype(school):
    style = (getattr(school, 'training_style', '') or '').lower()
    if style in ARCHETYPE_BY_STYLE:
        return ARCHETYPE_BY_STYLE[style]

    focus = (getattr(school, 'focus', '') or '').lower()
    for buckets, label in FOCUS_ARCHETYPE_RULES:
        if focus in buckets:
            return label

    return DEFAULT_COACH_ARCHETYPE


def _roll_scouting_ability(school):
    network = _decode_scouting_network(getattr(school, 'scouting_network', None))
    local = network.get('Local', 50)
    regional = network.get('Regional', 40)
    national = network.get('National', 30)
    international = network.get('International', 20)

    reach_score = (local * 0.4) + (regional * 0.6) + (national * 0.8) + international
    prestige = getattr(school, 'prestige', 50) or 50
    base = 35 + (prestige * 0.35) + (reach_score * 0.2)

    era = (getattr(school, 'current_era', '') or '').upper()
    if era == "DYNASTY":
        base += 8
    elif era == "ASCENDING":
        base += 4
    elif era == "REBUILDING":
        base -= 4
    elif era == "RETOOLING":
        base -= 1

    base += (getattr(school, 'era_momentum', 0) or 0) * 0.4

    style = (getattr(school, 'training_style', '') or '').lower()
    if style == "modern":
        base += 3
    elif style == "technical":
        base += 2
    elif style == "spirit":
        base -= 2

    noise = random.randint(-5, 5)
    return int(max(30, min(95, round(base + noise))))

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
    coach_archetype = _infer_coach_archetype(school)
    scouting_rating = _roll_scouting_ability(school)

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
        archetype=coach_archetype,
        scouting_ability=scouting_rating,
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