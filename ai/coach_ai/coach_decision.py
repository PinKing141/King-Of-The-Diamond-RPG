# ai/coach_ai/coach_decision.py
from database.setup_db import Player, Coach, PlayerGameStats, BatteryTrust
from sqlalchemy import desc


def _trait(coach, name, default=50):
    value = getattr(coach, name, None)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def calculate_player_utility(player, coach, team_avg_overall, session):
    """
    The Universal Utility Formula:
    Utility = (Stats * W_Stats) + (Trust * W_Trust) + (Seniority * W_Seniority) 
              + (Form * 0.2) - (Fatigue * W_Fatigue_Penalty)
    """
    # 1. Stats Score (0-100)
    # Use overall if available, or calculate simple average of key stats
    stats_score = player.overall if player.overall else (player.contact + player.power + player.fielding) / 3
    if player.position == "Pitcher":
        stats_score = (player.velocity + player.control + player.stamina) / 3
    
    # 2. Seniority Score (0-100)
    # Year 1 = 20, Year 2 = 60, Year 3 = 100
    seniority_map = {1: 20, 2: 60, 3: 100}
    seniority_score = seniority_map.get(player.year, 20)
    
    # 3. Trust Score (0-100)
    # Uses the player's baseline trust/discipline
    trust_score = player.trust_baseline
    
    # 4. Recent Form (0-100)
    # Calculated from last 5 games
    form_score = calculate_recent_form(player, session)
    
    # 5. Fatigue Score (0-100)
    fatigue_score = player.fatigue

    # --- APPLY WEIGHTS ---
    # Weights come from the Coach object (derived from Philosophy + Personality)
    
    w_stats = coach.stats_weight
    w_seniority = coach.seniority_weight
    w_trust = coach.trust_weight
    w_fatigue = coach.fatigue_penalty_weight
    
    raw_utility = (stats_score * w_stats) + \
                  (trust_score * w_trust) + \
                  (seniority_score * w_seniority) + \
                  (form_score * 0.2) - \
                  (fatigue_score * w_fatigue)

    # Personality nudges
    coach_drive = _trait(coach, 'drive')
    coach_loyalty = _trait(coach, 'loyalty')
    coach_volatility = _trait(coach, 'volatility')

    # Driven coaches demand excellence and add pressure for high performers
    drive_delta = (coach_drive - 50) * 0.2
    if stats_score >= team_avg_overall and drive_delta > 0:
        raw_utility += drive_delta
    elif stats_score < team_avg_overall and drive_delta > 0:
        raw_utility += drive_delta * 0.3

    # Low loyalty = faster disciplinary swings for bad form / mistakes
    if coach_loyalty < 55:
        impatience = (55 - coach_loyalty) / 55.0
        sloppy_play = max(0, 55 - form_score)
        raw_utility -= sloppy_play * impatience * 0.6
        # fatigue complaints are treated harshly as well
        extra_fatigue_penalty = max(0, fatigue_score - 40) * impatience * 0.25
        raw_utility -= extra_fatigue_penalty
    else:
        # Loyal coaches cushion the blow for small slumps
        forgiveness = (coach_loyalty - 55) / 45.0
        raw_utility += max(0, 55 - form_score) * forgiveness * 0.3

    # Volatile coaches are erratic: they overreact to both hot streaks and mistakes
    volatility_scalar = (coach_volatility - 50) / 50.0
    if volatility_scalar > 0:
        raw_utility += (form_score - 50) * 0.2 * volatility_scalar
        raw_utility -= max(0, fatigue_score - 50) * 0.3 * volatility_scalar

    # --- FAIRNESS RULES OVERRIDES ---
    
    # Rule 1: Talent Floor
    # If a player is a "Supernova" (+10 above team avg), they MUST play.
    # We artificially boost their utility to ensure they start.
    if stats_score > (team_avg_overall + 10):
        raw_utility += 50 # Massive boost
        
    # Rule 2: Grace Period (Prevent flickering)
    # If recently promoted (needs tracking, skipped for now or check history)
    
    # Rule 3: Freshman Protection (Handled in roster manager via "Development Slots")
    
    return raw_utility

def calculate_recent_form(player, session):
    """
    Averages performance rating of last 5 games.
    Returns 50 (Average) if no games played.
    """
    recent_games = session.query(PlayerGameStats).filter_by(player_id=player.id)\
                          .order_by(desc(PlayerGameStats.game_id)).limit(5).all()
    
    if not recent_games:
        return 50.0
        
    ratings = []
    for g in recent_games:
        # Simple Game Score approximation
        if player.position == "Pitcher":
            # ERA-like logic: Good = Low Runs, High K
            score = 50 + (g.strikeouts_pitched * 5) - (g.runs_allowed * 10) + (g.innings_pitched * 3)
        else:
            # OPS-like logic: Good = Hits, RBI
            score = 50 + (g.hits * 5) + (g.rbi * 5) + (g.runs * 2) - (g.strikeouts * 2)
        ratings.append(score)
        
    return sum(ratings) / len(ratings)