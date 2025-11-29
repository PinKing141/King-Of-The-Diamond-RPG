import random

def advance_runners(state, hit_type, batter):
    """
    Moves runners based on hit type.
    Updates state.runners and returns runs scored on this play.
    """
    scored_on_play = 0
    
    # Snapshot of who is where before moving
    r1 = state.runners[0] # 1st Base
    r2 = state.runners[1] # 2nd Base
    r3 = state.runners[2] # 3rd Base
    
    # Clear bases initially, we will repopulate them
    state.runners = [None, None, None]
    
    if hit_type == "HR":
        scored_on_play = 1 # Batter scores
        if r3: scored_on_play += 1
        if r2: scored_on_play += 1
        if r1: scored_on_play += 1
        # Bases remain empty
        
    elif hit_type == "1B":
        # R3 Scores
        if r3: 
            scored_on_play += 1
            
        # R2 Logic: Score or stop at 3rd?
        if r2:
            runner_speed = getattr(r2, 'speed', 50) # Use 'speed' attribute
            if runner_speed > 65 and random.random() > 0.4:
                scored_on_play += 1 # Scored from 2nd on a single
            else:
                state.runners[2] = r2 # Stop at 3rd
        
        # R1 goes to 2nd
        if r1: 
            # Aggressive running check from 1st to 3rd?
            runner_speed = getattr(r1, 'speed', 50)
            if state.runners[2] is None and runner_speed > 80: # 3rd is open
                state.runners[2] = r1 # 1st to 3rd
            else:
                state.runners[1] = r1 # Stop at 2nd
                
        # Batter to 1st
        state.runners[0] = batter

    elif hit_type == "2B":
        # R3 Scores
        if r3: scored_on_play += 1
        # R2 Scores
        if r2: scored_on_play += 1
        
        # R1 Logic: Score or stop at 3rd?
        if r1:
            runner_speed = getattr(r1, 'speed', 50)
            if runner_speed > 60:
                scored_on_play += 1 # Scored from 1st
            else:
                state.runners[2] = r1 # Stop at 3rd
        
        # Batter to 2nd
        state.runners[1] = batter

    elif hit_type == "3B":
        if r3: scored_on_play += 1
        if r2: scored_on_play += 1
        if r1: scored_on_play += 1
        state.runners[2] = batter

    return scored_on_play

def resolve_steal_attempt(runner, pitcher, catcher, target_base):
    """
    Calculates if a steal is successful.
    Returns: (bool is_safe, str description)
    """
    # Simple formula: Speed + Jump vs Pitcher Hold + Catcher Arm
    speed = getattr(runner, 'speed', 50)
    jump = random.randint(0, 20) # Jump quality
    
    pitcher_hold = getattr(pitcher, 'control', 50) / 2 # Pitchers with good control hold better? Or separate stat
    catcher_arm = getattr(catcher, 'throwing', 50) # Use throwing for arm strength
    
    attack = speed + jump
    defense = pitcher_hold + catcher_arm + random.randint(0, 10)
    
    if attack > defense:
        return True, "SAFE! Stolen Base."
    else:
        return False, "OUT! Caught Stealing."