# battery_system/pitcher_personality.py
import random

# Personality Definitions
# shake_prob: Base chance to shake off a sign they dislike.
# trust_factor: How much High Trust reduces shake-off chance.
PERSONALITIES = {
    "Stubborn": {
        "shake_prob": 0.50, 
        "trust_factor": 0.2, 
        "description": "Trusts their own gut. Hard to convince."
    },
    "Confident": {
        "shake_prob": 0.30, 
        "trust_factor": 0.4, 
        "description": "Believes they can throw anything, but has preferences."
    },
    "Nervous": {
        "shake_prob": 0.10, 
        "trust_factor": 0.8, 
        "description": "Relies heavily on the Catcher. Rarely shakes off."
    },
    "Agreeable": {
        "shake_prob": 0.05, 
        "trust_factor": 0.9, 
        "description": "Goes with the flow. Easy to manage."
    }
}

def get_pitcher_personality(pitcher):
    """
    Returns the personality dict for a pitcher.
    Defaults to 'Confident' if not set.
    """
    p_type = getattr(pitcher, 'pitcher_personality', 'Confident')
    if p_type not in PERSONALITIES:
        p_type = 'Confident'
    return PERSONALITIES[p_type]

def does_pitcher_accept(pitcher, suggested_pitch, trust_level, *, dominance: float = 0.0):
    """
    AI Logic: Decides if an AI Pitcher accepts the Catcher's sign.
    """
    personality = get_pitcher_personality(pitcher)
    
    # Base Probability to Shake
    shake_chance = personality['shake_prob']
    
    # Trust Modifier: Higher trust = Lower shake chance
    # (trust - 50) * factor -> reduces probability
    trust_mod = ((trust_level - 50) / 100.0) * personality['trust_factor']
    shake_chance -= trust_mod
    shake_chance -= dominance * 0.05
    
    # Preference Modifier: Does the pitcher like this pitch?
    # (Simplified: If it's their best pitch (highest quality), they like it)
    # logic: if suggested_pitch.quality > 60 -> shake_chance -= 0.2
    
    if random.random() < shake_chance:
        return False # Shake off
    return True # Accept