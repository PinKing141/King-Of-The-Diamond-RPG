# pitch_definitions.py
# Defines the physics and attributes for all pitch types in the game.

ARM_SLOT_MODIFIERS = {
    # Vertical (Y) / Horizontal (X) multipliers and general risk
    "Overhand": {
        "vertical_mult": 1.3,
        "horizontal_mult": 0.7,
        "control_penalty_mult": 0.95, # Slightly better control on average
        "stamina_cost_mult": 1.1,
        "risk_type": "Shoulder"
    },
    "Three-Quarters": {
        "vertical_mult": 1.0,
        "horizontal_mult": 1.0,
        "control_penalty_mult": 1.0,
        "stamina_cost_mult": 1.0,
        "risk_type": "Balanced"
    },
    "Sidearm": {
        "vertical_mult": 0.3, # Flattens vertical drop
        "horizontal_mult": 1.7, # Extreme lateral break
        "control_penalty_mult": 1.2, # Harder to spot target (Higher variance)
        "stamina_cost_mult": 0.9,
        "risk_type": "Elbow"
    },
    "Submarine": {
        "vertical_mult": 0.1, # Almost pure horizontal/rising action
        "horizontal_mult": 2.0, # Maximum lateral break
        "control_penalty_mult": 1.5, # Very difficult to control
        "stamina_cost_mult": 0.8,
        "risk_type": "Knee/Back"
    }
}

PITCH_TYPES = {
    # --- FASTBALLS ---
    "4-Seam Fastball": {"velocity_mod": 1.0, "break_mod": 0.1, "stamina_cost": 1.0, "type": "Vertical", "desc": "Pure speed."},
    "2-Seam Fastball": {"velocity_mod": 0.96, "break_mod": 0.4, "stamina_cost": 1.0, "type": "Horizontal", "desc": "Tailing action."},
    "Shuuto": {"velocity_mod": 0.94, "break_mod": 0.6, "stamina_cost": 1.1, "type": "Horizontal", "desc": "Sharp inside break."},
    "Cutter": {"velocity_mod": 0.95, "break_mod": 0.5, "stamina_cost": 1.1, "type": "Horizontal", "desc": "Late cut."},

    # --- BREAKING BALLS ---
    "Slider": {"velocity_mod": 0.88, "break_mod": 0.8, "stamina_cost": 1.2, "type": "Horizontal", "desc": "Lateral break."},
    "Curveball": {"velocity_mod": 0.78, "break_mod": 1.0, "stamina_cost": 1.1, "type": "Vertical", "desc": "Big drop."},
    "Slow Curve": {"velocity_mod": 0.65, "break_mod": 1.2, "stamina_cost": 0.9, "type": "Vertical", "desc": "Timing disruptor."},
    "Slurve": {"velocity_mod": 0.82, "break_mod": 0.9, "stamina_cost": 1.2, "type": "Diagonal", "desc": "Fast breaker."},

    # --- DROP/SINK ---
    "Forkball": {"velocity_mod": 0.85, "break_mod": 0.9, "stamina_cost": 1.4, "type": "Vertical", "desc": "Drops off table."},
    "Splitter": {"velocity_mod": 0.90, "break_mod": 0.7, "stamina_cost": 1.2, "type": "Vertical", "desc": "Late dive."},
    "Sinker": {"velocity_mod": 0.92, "break_mod": 0.6, "stamina_cost": 1.1, "type": "Drop_Sink", "desc": "Heavy ball."},
    
    # --- OFFSPEED ---
    "Changeup": {"velocity_mod": 0.82, "break_mod": 0.4, "stamina_cost": 0.9, "type": "Offspeed", "desc": "Speed deception."},
    "Circle Change": {"velocity_mod": 0.80, "break_mod": 0.6, "stamina_cost": 0.9, "type": "Offspeed", "desc": "Fading action."},
    "Knuckleball": {"velocity_mod": 0.60, "break_mod": 1.5, "stamina_cost": 0.5, "type": "Erratic", "desc": "Unpredictable."}
}