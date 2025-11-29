import random

class ContactResult:
    def __init__(self, hit_type, description, rbi=0, outs=0):
        self.hit_type = hit_type # "Out", "1B", "2B", "3B", "HR"
        self.description = description
        self.rbi = rbi
        self.outs = outs

def resolve_contact(contact_quality, batter, pitcher, power_mod=0):
    """
    Determines the result of a ball put in play.
    Uses contact_quality from pitch_logic + Batter Power + Randomness.
    Accepts 'power_mod' from User Input (Power Swing).
    """
    
    # Apply Power Mod (e.g. +25 from Power Swing)
    raw_power = batter.power + power_mod
    power_transfer = raw_power + random.randint(0, 20)
    
    # Determine Trajectory
    if contact_quality < 35:
        trajectory = "Grounder"
    elif contact_quality < 65:
        trajectory = "Fly"
    elif contact_quality < 85:
        trajectory = "Line Drive"
    else:
        trajectory = "Gapper" if power_transfer < 80 else "Deep Fly"

    # Resolve Outcome based on Trajectory & Speed/Power
    hit_type = "Out"
    desc = "Out"
    
    if trajectory == "Grounder":
        if contact_quality < 20:
            desc = "Weak dribbler to the mound."
        else:
            # Speed check for infield single
            if batter.running > 75 and random.random() > 0.65:
                hit_type = "1B"
                desc = "Infield Single! Beat the throw."
            else:
                desc = "Ground out."
                
    elif trajectory == "Fly":
        desc = "Pop fly caught."
        
    elif trajectory == "Line Drive":
        if random.random() > 0.35: 
            hit_type = "1B"
            desc = "Clean single to center."
        else:
            desc = "Line drive... CAUGHT!"
            
    elif trajectory == "Gapper":
        if batter.running > 60:
            hit_type = "2B"
            desc = "Double into the gap!"
        else:
            hit_type = "1B"
            desc = "Long single off the wall."
            
    elif trajectory == "Deep Fly":
        if power_transfer > 85:
            hit_type = "HR"
            desc = "HOME RUN! Gone!"
        elif power_transfer > 70:
            hit_type = "2B"
            desc = "Off the wall! Double."
        else:
            desc = "Deep fly out at the warning track."

    return ContactResult(hit_type, desc)