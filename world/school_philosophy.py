# world/school_philosophy.py
import random

# THE PHILOSOPHY MATRIX
# Defines how different schools approach the game.
# Includes prestige ranges, AI weights, and training styles.

PHILOSOPHY_MATRIX = {
    # --- ELITE TIER (Prestige 85+) ---
    "Supreme Dynasty": {
        "prestige_range": (90, 100),
        "budget": 1000000,
        "focus": "Balanced",
        "training_style": "Modern",
        "seniority_bias": 0.1,    # Pure Meritocracy
        "trust_weight": 0.3,
        "stats_weight": 0.8,
        "injury_tolerance": -0.5, # Protect assets
        "description": "The absolute rulers of High School baseball. Victory is expected."
    },
    "National Brand": {
        "prestige_range": (80, 95),
        "budget": 800000,
        "focus": "Balanced",
        "training_style": "Technical",
        "seniority_bias": 0.2,
        "trust_weight": 0.4,
        "stats_weight": 0.7,
        "injury_tolerance": -0.2,
        "description": "A famous school known in every household. Consistent and strong."
    },
    "Pitching Kingdom": {
        "prestige_range": (75, 90),
        "budget": 600000,
        "focus": "Pitching",
        "training_style": "Technical",
        "seniority_bias": 0.3,
        "trust_weight": 0.5,
        "stats_weight": 0.6,
        "injury_tolerance": -0.6, # Arms are precious
        "description": "Built on a dynasty of aces. Defense and pitching win championships."
    },
    "Elite Battery": {
        "prestige_range": (75, 90),
        "budget": 600000,
        "focus": "Battery",
        "training_style": "Technical",
        "seniority_bias": 0.3,
        "trust_weight": 0.9,      # Critical for battery schools
        "stats_weight": 0.4,
        "injury_tolerance": -0.4,
        "description": "Specialists in the art of the battery. The catcher controls the game."
    },

    # --- OFFENSIVE POWERHOUSES (Prestige 60-85) ---
    "Slugger Army": {
        "prestige_range": (65, 85),
        "budget": 400000,
        "focus": "Power",
        "training_style": "Modern",
        "seniority_bias": 0.2,
        "trust_weight": 0.2,
        "stats_weight": 0.9,      # OPS is king
        "injury_tolerance": 0.3,
        "description": "Overwhelming offense. We score 10 runs, so giving up 9 is fine."
    },
    "Machine Gunners": {
        "prestige_range": (60, 80),
        "budget": 350000,
        "focus": "Contact",
        "training_style": "Technical",
        "seniority_bias": 0.2,
        "trust_weight": 0.4,
        "stats_weight": 0.8,
        "injury_tolerance": 0.1,
        "description": "Relentless string of hits. Keep the line moving."
    },
    "Glass Cannons": {
        "prestige_range": (55, 75),
        "budget": 300000,
        "focus": "Power",
        "training_style": "Modern",
        "seniority_bias": 0.1,
        "trust_weight": 0.1,
        "stats_weight": 0.9,
        "injury_tolerance": 0.5,  # High risk high reward
        "description": "All offense, no defense. Every game is a shootout."
    },
    "Clean-Up Crew": {
        "prestige_range": (60, 75),
        "budget": 350000,
        "focus": "Core",
        "training_style": "Modern",
        "seniority_bias": 0.4,
        "trust_weight": 0.4,
        "stats_weight": 0.6,
        "injury_tolerance": 0.0,
        "description": "Built around a devastating 3-4-5 lineup core."
    },

    # --- SPEED & TACTICS ---
    "Small Ball Cult": {
        "prestige_range": (45, 65),
        "budget": 200000,
        "focus": "Speed",
        "training_style": "Technical",
        "seniority_bias": 0.3,
        "trust_weight": 0.7,      # Execution requires trust
        "stats_weight": 0.4,
        "injury_tolerance": 0.0,
        "description": "Bunt, steal, squeeze. A nightmare to defend against."
    },
    "Speed Demons": {
        "prestige_range": (50, 70),
        "budget": 250000,
        "focus": "Speed",
        "training_style": "Modern",
        "seniority_bias": 0.2,
        "trust_weight": 0.3,
        "stats_weight": 0.7,
        "injury_tolerance": 0.1,
        "description": "Athleticism above all. Chaos on the basepaths."
    },
    
    # --- TECHNICAL & DEFENSIVE ---
    "Precision Machines": {
        "prestige_range": (65, 80),
        "budget": 400000,
        "focus": "Technical",
        "training_style": "Technical",
        "seniority_bias": 0.3,
        "trust_weight": 0.5,
        "stats_weight": 0.7,
        "injury_tolerance": -0.2,
        "description": "Robot-like execution. They simply do not make mistakes."
    },
    "Scientific": {
        "prestige_range": (60, 75),
        "budget": 450000,
        "focus": "Technical",
        "training_style": "Modern",
        "seniority_bias": 0.0,    # Pure Data
        "trust_weight": 0.1,
        "stats_weight": 1.0,      # Data driven
        "injury_tolerance": -0.5,
        "description": "Baseball is physics. Strategy is math."
    },
    "Defensive Wall": {
        "prestige_range": (55, 75),
        "budget": 250000,
        "focus": "Defense",
        "training_style": "Spirit",
        "seniority_bias": 0.5,
        "trust_weight": 0.6,
        "stats_weight": 0.3,
        "injury_tolerance": 0.4,
        "description": "You can't lose if you don't give up runs."
    },
    "Iron Infield": {
        "prestige_range": (55, 70),
        "budget": 250000,
        "focus": "Defense",
        "training_style": "Technical",
        "seniority_bias": 0.4,
        "trust_weight": 0.6,
        "stats_weight": 0.4,
        "injury_tolerance": 0.0,
        "description": "An impenetrable infield defense."
    },
    "No-Fly Zone": {
        "prestige_range": (50, 65),
        "budget": 200000,
        "focus": "Defense",
        "training_style": "Technical",
        "seniority_bias": 0.3,
        "trust_weight": 0.5,
        "stats_weight": 0.5,
        "injury_tolerance": 0.0,
        "description": "Elite outfielders who catch everything."
    },
    "Catcher General": {
        "prestige_range": (50, 65),
        "budget": 200000,
        "focus": "Battery",
        "training_style": "Spirit",
        "seniority_bias": 0.6,
        "trust_weight": 0.9,      # Absolute trust in catcher
        "stats_weight": 0.2,
        "injury_tolerance": 0.3,
        "description": "The team moves at the command of their captain catcher."
    },

    # --- SPIRIT & STAMINA ---
    "Militaristic": {
        "prestige_range": (45, 60),
        "budget": 150000,
        "focus": "Stamina",
        "training_style": "Spirit",
        "seniority_bias": 0.9,    # Rank is absolute
        "trust_weight": 0.7,
        "stats_weight": 0.1,
        "injury_tolerance": 0.9,  # Pain is weakness leaving the body
        "description": "Strict hierarchy and endless drilling."
    },
    "Guts & Glory": {
        "prestige_range": (40, 55),
        "budget": 100000,
        "focus": "Guts",
        "training_style": "Spirit",
        "seniority_bias": 0.5,
        "trust_weight": 0.8,
        "stats_weight": 0.1,
        "injury_tolerance": 1.0,  # Never give up
        "description": "Fighting spirit (Konjo) wins games, not skill."
    },
    "Marathon Men": {
        "prestige_range": (45, 60),
        "budget": 150000,
        "focus": "Stamina",
        "training_style": "Spirit",
        "seniority_bias": 0.4,
        "trust_weight": 0.4,
        "stats_weight": 0.4,
        "injury_tolerance": 0.7,
        "description": "They will outlast you in extra innings."
    },
    "Zen Baseball": {
        "prestige_range": (55, 70),
        "budget": 250000,
        "focus": "Mental",
        "training_style": "Spirit",
        "seniority_bias": 0.5,
        "trust_weight": 0.7,
        "stats_weight": 0.3,
        "injury_tolerance": 0.0,
        "description": "Focus, breathing, and perfect mental state."
    },

    # --- SPECIAL TYPES ---
    "One-Man Army": {
        "prestige_range": (35, 50),
        "budget": 100000,
        "focus": "Ace",
        "training_style": "Spirit",
        "seniority_bias": 0.5,
        "trust_weight": 0.8,
        "stats_weight": 0.4,
        "injury_tolerance": 0.6,
        "description": "The entire team exists to support one superstar Ace."
    },
    "Twin Aces": {
        "prestige_range": (55, 70),
        "budget": 300000,
        "focus": "Pitching",
        "training_style": "Modern",
        "seniority_bias": 0.2,
        "trust_weight": 0.4,
        "stats_weight": 0.7,
        "injury_tolerance": -0.3,
        "description": "Relies on a dominant 1-2 punch rotation."
    },
    "Fallen Giant": {
        "prestige_range": (70, 85),
        "budget": 500000,
        "focus": "Balanced",
        "training_style": "Traditional",
        "seniority_bias": 0.8,    # Stuck in old ways
        "trust_weight": 0.5,
        "stats_weight": 0.3,
        "injury_tolerance": 0.2,
        "description": "A former powerhouse trying to reclaim glory."
    },
    "Public School Hero": {
        "prestige_range": (35, 50),
        "budget": 80000,
        "focus": "Guts",
        "training_style": "Spirit",
        "seniority_bias": 0.6,
        "trust_weight": 0.9,
        "stats_weight": 0.2,
        "injury_tolerance": 0.8,
        "description": "The local underdog supported by the whole town."
    },
    "Academic Elite": {
        "prestige_range": (70, 85),
        "budget": 500000,
        "focus": "Technical",
        "training_style": "Modern",
        "seniority_bias": 0.2,
        "trust_weight": 0.3,
        "stats_weight": 0.9,
        "injury_tolerance": -0.5,
        "description": "Smart players who analyze every play."
    },
    "Rich Private School": {
        "prestige_range": (65, 80),
        "budget": 900000,
        "focus": "Balanced",
        "training_style": "Modern",
        "seniority_bias": 0.3,
        "trust_weight": 0.4,
        "stats_weight": 0.6,
        "injury_tolerance": -0.4,
        "description": "Excellent facilities and equipment."
    },
    
    # --- RAGTAG & OTHERS ---
    "Delinquent Squad": {
        "prestige_range": (20, 40),
        "budget": 50000,
        "focus": "Power",
        "training_style": "Spirit",
        "seniority_bias": 0.8,    # Boss rule
        "trust_weight": 0.8,
        "stats_weight": 0.2,
        "injury_tolerance": 0.9,
        "description": "Rough, undisciplined, but terrifyingly strong."
    },
    "Modern Freedom": {
        "prestige_range": (45, 60),
        "budget": 200000,
        "focus": "Balanced",
        "training_style": "Modern",
        "seniority_bias": 0.0,    # Players decide
        "trust_weight": 0.5,
        "stats_weight": 0.5,
        "injury_tolerance": -0.2,
        "description": "No shaved heads, player autonomy, loose atmosphere."
    },
    "Dark Horse": {
        "prestige_range": (35, 55),
        "budget": 100000,
        "focus": "Random",
        "training_style": "Hybrid",
        "seniority_bias": 0.3,
        "trust_weight": 0.5,
        "stats_weight": 0.5,
        "injury_tolerance": 0.2,
        "description": "Unpredictable. Could beat anyone on a good day."
    },
    "Gamblers": {
        "prestige_range": (30, 45),
        "budget": 80000,
        "focus": "Random",
        "training_style": "Modern",
        "seniority_bias": 0.2,
        "trust_weight": 0.2,
        "stats_weight": 0.4,
        "injury_tolerance": 0.5,
        "description": "High risk strategies are the norm."
    },
    "Local Bully": {
        "prestige_range": (30, 45),
        "budget": 80000,
        "focus": "Power",
        "training_style": "Spirit",
        "seniority_bias": 0.7,
        "trust_weight": 0.3,
        "stats_weight": 0.3,
        "injury_tolerance": 0.6,
        "description": "Dominates weak teams, struggles against real pros."
    },
    "Average Joes": {
        "prestige_range": (25, 40),
        "budget": 50000,
        "focus": "Balanced",
        "training_style": "Hybrid",
        "seniority_bias": 0.4,
        "trust_weight": 0.5,
        "stats_weight": 0.5,
        "injury_tolerance": 0.0,
        "description": "Just regular high school kids playing ball."
    }
}

# Define frequencies for random selection (approximate based on 'weight')
PHILOSOPHY_WEIGHTS = {
    "Supreme Dynasty": 1, "National Brand": 2, "Pitching Kingdom": 2, "Elite Battery": 2,
    "Slugger Army": 4, "Machine Gunners": 4, "Glass Cannons": 4, "Clean-Up Crew": 4,
    "Small Ball Cult": 6, "Speed Demons": 6, "Precision Machines": 5, "Scientific": 5,
    "Defensive Wall": 6, "Iron Infield": 6, "No-Fly Zone": 6, "Catcher General": 6,
    "Militaristic": 5, "Guts & Glory": 5, "Marathon Men": 5, "Zen Baseball": 4,
    "One-Man Army": 3, "Twin Aces": 3, "Fallen Giant": 2, "Public School Hero": 3,
    "Academic Elite": 2, "Rich Private School": 2, "Delinquent Squad": 3, "Modern Freedom": 3,
    "Dark Horse": 8, "Gamblers": 8, "Local Bully": 8, "Average Joes": 10
}

def get_philosophy(name=None):
    """Returns the dictionary for a specific philosophy or a random one based on weight."""
    if name and name in PHILOSOPHY_MATRIX:
        return name, PHILOSOPHY_MATRIX[name]
    
    # Weighted random selection
    keys = list(PHILOSOPHY_WEIGHTS.keys())
    weights = list(PHILOSOPHY_WEIGHTS.values())
    
    selected_key = random.choices(keys, weights=weights, k=1)[0]
    return selected_key, PHILOSOPHY_MATRIX[selected_key]