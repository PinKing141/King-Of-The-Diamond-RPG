import random
from sqlalchemy.orm import sessionmaker
from database.setup_db import Player, School, PitchRepertoire, engine # Updated imports

Session = sessionmaker(bind=engine)
session = Session()

class MatchState:
    """
    The Central Nervous System of the match.
    Holds all state: Score, Innings, Runners, Counts, Stats.
    Passed to every logic module.
    """
    def __init__(self, home_team, away_team, home_lineup, away_lineup, home_pitcher, away_pitcher):
        # Teams (Now Schools)
        self.home_team = home_team
        self.away_team = away_team
        
        # Lineups (List of Player objects)
        self.home_lineup = home_lineup
        self.away_lineup = away_lineup
        
        # Current Pitchers
        self.home_pitcher = home_pitcher
        self.away_pitcher = away_pitcher
        
        # Game State
        self.inning = 1
        self.top_bottom = "Top" # "Top" or "Bot"
        self.outs = 0
        self.strikes = 0
        self.balls = 0
        
        # Runners: [1B, 2B, 3B] -> Contains Player objects or None
        self.runners = [None, None, None]
        
        # Scores
        self.home_score = 0
        self.away_score = 0
        self.inning_scores = [] 
        
        # Stats Tracking (Live)
        self.stats = {} 
        self.pitch_counts = {}
        
        # Log/Commentary Buffer
        self.logs = []

    def get_stats(self, p_id):
        if p_id not in self.stats:
            self.stats[p_id] = {
                "at_bats": 0, "hits": 0, "homeruns": 0, "rbi": 0,
                "strikeouts": 0, "walks": 0, "runs_allowed": 0,
                "strikeouts_pitched": 0, "innings_pitched": 0.0, "pitches": 0
            }
        return self.stats[p_id]

    def add_pitch_count(self, pitcher_id):
        self.pitch_counts[pitcher_id] = self.pitch_counts.get(pitcher_id, 0) + 1
        return self.pitch_counts[pitcher_id]

    def reset_count(self):
        self.strikes = 0
        self.balls = 0

    def clear_bases(self):
        self.runners = [None, None, None]
        
    def log(self, message):
        self.logs.append(message)

def prepare_match(home_id, away_id):
    """
    Loads teams, builds lineups, selects pitchers.
    Returns a ready-to-use MatchState object.
    """
    # Use School model, use session.get()
    home_team = session.get(School, home_id)
    away_team = session.get(School, away_id)
    
    if not home_team or not away_team:
        print("Error: One of the teams could not be found.")
        return None

    # Corrected filtering: Use school_id instead of team_id
    home_players = session.query(Player).filter_by(school_id=home_id).order_by(Player.jersey_number).all()
    away_players = session.query(Player).filter_by(school_id=away_id).order_by(Player.jersey_number).all()
    
    # Lineup Logic (First 9 non-pitchers, or just first 9 if small roster)
    # Ideally, Roster Manager has set 'is_starter'
    
    home_lineup = [p for p in home_players if p.is_starter][:9]
    if len(home_lineup) < 9: # Fallback
        home_lineup = home_players[:9]

    away_lineup = [p for p in away_players if p.is_starter][:9]
    if len(away_lineup) < 9:
        away_lineup = away_players[:9]
    
    # Select Pitcher
    # Try to find assigned 'ACE' or 'STARTER' pitcher role
    home_pitcher = next((p for p in home_players if p.position == 'Pitcher' and p.role == 'ACE'), None)
    if not home_pitcher: home_pitcher = next((p for p in home_players if p.position == 'Pitcher'), home_players[0])
    
    away_pitcher = next((p for p in away_players if p.position == 'Pitcher' and p.role == 'ACE'), None)
    if not away_pitcher: away_pitcher = next((p for p in away_players if p.position == 'Pitcher'), away_players[0])
    
    return MatchState(home_team, away_team, home_lineup, away_lineup, home_pitcher, away_pitcher)