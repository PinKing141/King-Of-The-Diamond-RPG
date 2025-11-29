import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, synonym
import sys
import os

# Add parent directory to path to find config.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

# Make directory for DB if missing
db_dir = os.path.dirname(DB_PATH)
if not os.path.exists(db_dir):
    os.makedirs(db_dir)

engine = create_engine(f"sqlite:///{DB_PATH}")
Base = declarative_base()

# GLOBAL SESSION
Session = sessionmaker(bind=engine)
session = Session()


# ============================================================
# 1. SCHOOL TABLE
# ============================================================
class School(Base):
    __tablename__ = 'schools'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    prefecture = Column(String)
    prestige = Column(Integer, default=0)

    budget = Column(Integer, default=500000)

    # Philosophy data
    philosophy = Column(String)
    focus = Column(String)
    seniority_weight = Column(Float, default=0.5)
    trust_weight = Column(Float, default=0.5)
    stats_weight = Column(Float, default=0.5)
    injury_tolerance = Column(Float, default=0.0)
    training_style = Column(String, default="Modern")

    # Relationships
    players = relationship("Player", back_populates="school")
    coach = relationship("Coach", back_populates="school", uselist=False)
    games_home = relationship("Game", foreign_keys="Game.home_school_id", back_populates="home_school")
    games_away = relationship("Game", foreign_keys="Game.away_school_id", back_populates="away_school")
    scouting_data = relationship("ScoutingData", back_populates="school")


# ============================================================
# 2. COACH TABLE
# ============================================================
class Coach(Base):
    __tablename__ = 'coaches'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(Integer, ForeignKey('schools.id'))
    name = Column(String)

    tradition = Column(Float, default=0.5)
    logic = Column(Float, default=0.5)
    temper = Column(Float, default=0.5)
    ambition = Column(Float, default=0.5)

    seniority_weight = Column(Float, default=0.5)
    trust_weight = Column(Float, default=0.5)
    stats_weight = Column(Float, default=0.5)
    fatigue_penalty_weight = Column(Float, default=0.5)

    school = relationship("School", back_populates="coach")


# ============================================================
# 3. PLAYER TABLE (UPDATED WITH HEIGHT)
# ============================================================
class Player(Base):
    __tablename__ = 'players'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(Integer, ForeignKey('schools.id'))

    name = Column(String)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)

    year = Column(Integer)
    position = Column(String)
    jersey_number = Column(Integer)
    is_captain = Column(Boolean, default=False)
    is_starter = Column(Boolean, default=False)

    role = Column(String, default="BENCH")

    overall = Column(Integer, default=0)
    potential_grade = Column(String, default="C")
    growth_tag = Column(String, default="Normal")

    # Mental / Battery
    pitcher_personality = Column(String, nullable=True)
    catcher_leadership = Column(Integer, default=0)
    battery_xp = Column(Integer, default=0)
    trust_baseline = Column(Integer, default=50)
    mental = Column(Integer, default=50)
    discipline = Column(Integer, default=50)
    clutch = Column(Integer, default=50)

    # ---------- NEW PHYSICAL GROWTH ----------
    height_cm = Column(Integer, default=165)           # Starting height
    height_potential = Column(Integer, default=180)    # Max possible height

    # Attributes (batting + pitching)
    stamina = Column(Integer, default=50)
    velocity = Column(Integer, default=0)
    control = Column(Integer, default=0)
    command = Column(Integer, default=0)
    movement = Column(Integer, default=0)
    
    fielding = Column(Integer, default=0)
    speed = Column(Integer, default=0)
    contact = Column(Integer, default=0)
    power = Column(Integer, default=0)
    throwing = Column(Integer, default=0)

    # Status
    fatigue = Column(Integer, default=0)
    injury_status = Column(String, default="Healthy")
    injury_days = Column(Integer, default=0)
    conditioning = Column(Integer, default=50)

    school = relationship("School", back_populates="players")
    pitch_repertoire = relationship("PitchRepertoire", back_populates="player")


# ============================================================
# 4. BATTERY TRUST TABLE
# ============================================================
class BatteryTrust(Base):
    __tablename__ = 'battery_trust'
    
    pitcher_id = Column(Integer, ForeignKey('players.id'), primary_key=True)
    catcher_id = Column(Integer, ForeignKey('players.id'), primary_key=True)
    trust = Column(Integer, default=50)


# ============================================================
# 5. ROSTER TABLE
# ============================================================
class Roster(Base):
    __tablename__ = 'roster'
    
    school_id = Column(Integer, ForeignKey('schools.id'), primary_key=True)
    position = Column(String, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'))


# ============================================================
# 6. GAME TABLE
# ============================================================
class Game(Base):
    __tablename__ = 'games'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    home_school_id = Column(Integer, ForeignKey('schools.id'))
    away_school_id = Column(Integer, ForeignKey('schools.id'))

    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    date = Column(String, nullable=True)
    round = Column(String, default="Practice")
    season_year = Column(Integer, default=1)
    tournament = Column(String, nullable=True)
    is_completed = Column(Boolean, default=False)

    home_school = relationship("School", foreign_keys=[home_school_id], back_populates="games_home")
    away_school = relationship("School", foreign_keys=[away_school_id], back_populates="games_away")
    stats = relationship("PlayerGameStats", back_populates="game")


# ============================================================
# 7. PLAYER GAME STATS TABLE
# ============================================================
class PlayerGameStats(Base):
    __tablename__ = 'player_game_stats'
    
    game_id = Column(Integer, ForeignKey('games.id'), primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), primary_key=True)
    
    team_id = Column(Integer)

    innings_pitched = Column(Float, default=0.0)
    pitches_thrown = Column(Integer, default=0)
    hits = Column(Integer, default=0)
    runs = Column(Integer, default=0)
    strikeouts = Column(Integer, default=0)
    walks = Column(Integer, default=0)

    at_bats = Column(Integer, default=0)
    hits_batted = Column(Integer, default=0)
    rbi = Column(Integer, default=0)
    homeruns = Column(Integer, default=0)

    fielding_errors = Column(Integer, default=0)
    
    strikeouts_pitched = Column(Integer, default=0)
    runs_allowed = Column(Integer, default=0)

    game = relationship("Game", back_populates="stats")
    player = relationship("Player")


# ============================================================
# 8. SCOUTING DATA TABLE
# ============================================================
class ScoutingData(Base):
    __tablename__ = 'scouting_data'
    
    school_id = Column(Integer, ForeignKey('schools.id'), primary_key=True)

    knowledge_level = Column(Integer, default=0)
    rivalry_score = Column(Integer, default=0)
    last_scouted_week = Column(Integer, default=0)

    school = relationship("School", back_populates="scouting_data")


# ============================================================
# HELPER TABLES
# ============================================================
class PitchRepertoire(Base):
    __tablename__ = 'pitch_repertoire'
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'))

    pitch_name = Column(String)
    quality = Column(Integer)
    break_level = Column(Integer)

    player = relationship("Player", back_populates="pitch_repertoire")


class GameState(Base):
    __tablename__ = 'gamestate'
    id = Column(Integer, primary_key=True)
    current_day = Column(String)
    current_week = Column(Integer)
    current_month = Column(Integer)
    current_year = Column(Integer)


# Aliases
Team = School
Performance = PlayerGameStats


# ============================================================
# DATABASE INITIALISATION
# ============================================================
def create_database():
    Base.metadata.create_all(engine)
    
    if not session.query(GameState).first():
        print("Initialising Game State...")
        initial_state = GameState(
            current_day='MON',
            current_week=1,
            current_month=4,
            current_year=2024
        )
        session.add(initial_state)
        session.commit()


if __name__ == "__main__":
    create_database()