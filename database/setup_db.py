import sqlalchemy
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    Boolean,
    Text,
    DateTime,
    Index,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, synonym
from sqlalchemy import inspect
from contextlib import contextmanager
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

SessionLocal = sessionmaker(bind=engine)


def get_session():
    """Return a brand-new SQLAlchemy session."""
    return SessionLocal()


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def close_all_sessions():
    """Ensure every live session created via SessionLocal is closed."""
    SessionLocal.close_all()


def ensure_gamestate_schema():
    """Add new columns to gamestate table when upgrading existing saves."""
    inspector = inspect(engine)
    if not inspector.has_table('gamestate'):
        return

    columns = {col['name'] for col in inspector.get_columns('gamestate')}
    if 'active_player_id' not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE gamestate ADD COLUMN active_player_id INTEGER"))


def ensure_player_schema():
    """Add newly introduced player columns when upgrading existing saves."""
    inspector = inspect(engine)
    if not inspector.has_table('players'):
        return

    columns = {col['name'] for col in inspector.get_columns('players')}
    statements = []

    if 'height_cm' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN height_cm INTEGER DEFAULT 165")
    if 'height_potential' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN height_potential INTEGER DEFAULT 180")
    if 'growth_tag' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN growth_tag VARCHAR DEFAULT 'Normal'")
    if 'weight_kg' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN weight_kg INTEGER DEFAULT 72")
    if 'is_two_way' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN is_two_way BOOLEAN DEFAULT 0")
    if 'secondary_position' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN secondary_position VARCHAR")

    if 'academic_skill' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN academic_skill INTEGER DEFAULT 55")
    if 'test_score' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN test_score INTEGER DEFAULT 55")
    if 'drive' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN drive INTEGER DEFAULT 50")
    if 'loyalty' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN loyalty INTEGER DEFAULT 50")
    if 'volatility' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN volatility INTEGER DEFAULT 50")
    if 'morale' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN morale INTEGER DEFAULT 60")
    if 'slump_timer' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN slump_timer INTEGER DEFAULT 0")
    if 'archetype' not in columns:
        statements.append("ALTER TABLE players ADD COLUMN archetype VARCHAR DEFAULT 'steady'")

    if not statements:
        return

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def ensure_player_skill_schema():
    inspector = inspect(engine)
    if inspector.has_table('player_skills'):
        return

    PlayerSkill.__table__.create(bind=engine)


def ensure_player_milestone_schema():
    inspector = inspect(engine)
    if inspector.has_table('player_milestones'):
        return

    PlayerMilestone.__table__.create(bind=engine)


def ensure_coach_schema():
    inspector = inspect(engine)
    if not inspector.has_table('coaches'):
        return

    columns = {col['name'] for col in inspector.get_columns('coaches')}
    statements = []
    if 'drive' not in columns:
        statements.append("ALTER TABLE coaches ADD COLUMN drive INTEGER DEFAULT 50")
    if 'loyalty' not in columns:
        statements.append("ALTER TABLE coaches ADD COLUMN loyalty INTEGER DEFAULT 50")
    if 'volatility' not in columns:
        statements.append("ALTER TABLE coaches ADD COLUMN volatility INTEGER DEFAULT 50")

    if not statements:
        return

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.execute(text("UPDATE coaches SET drive = COALESCE(drive, 50)"))
        conn.execute(text("UPDATE coaches SET loyalty = COALESCE(loyalty, 50)"))
        conn.execute(text("UPDATE coaches SET volatility = COALESCE(volatility, 50)"))


def ensure_game_stats_schema():
    inspector = inspect(engine)
    if not inspector.has_table('player_game_stats'):
        return

    columns = {col['name'] for col in inspector.get_columns('player_game_stats')}
    statements = []
    if 'confidence' not in columns:
        statements.append("ALTER TABLE player_game_stats ADD COLUMN confidence INTEGER DEFAULT 0")

    if not statements:
        return

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def ensure_game_schema():
    inspector = inspect(engine)
    if not inspector.has_table('games'):
        return

    columns = {col['name'] for col in inspector.get_columns('games')}
    statements = []

    def _add(col_name, definition):
        if col_name not in columns:
            statements.append(f"ALTER TABLE games ADD COLUMN {col_name} {definition}")

    _add('weather_label', 'VARCHAR')
    _add('weather_condition', 'VARCHAR')
    _add('weather_precip', 'VARCHAR')
    _add('weather_temperature_f', 'INTEGER')
    _add('weather_wind_speed', 'FLOAT')
    _add('weather_wind_direction', 'VARCHAR')
    _add('weather_summary', 'TEXT')
    _add('umpire_name', 'VARCHAR')
    _add('umpire_description', 'TEXT')
    _add('umpire_zone_bias', 'FLOAT')
    _add('umpire_home_bias', 'FLOAT')
    _add('umpire_temperament', 'FLOAT')
    _add('umpire_favored_home', 'INTEGER')
    _add('umpire_squeezed_home', 'INTEGER')
    _add('umpire_favored_away', 'INTEGER')
    _add('umpire_squeezed_away', 'INTEGER')

    if not statements:
        return

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


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

    drive = Column(Integer, default=50)
    loyalty = Column(Integer, default=50)
    volatility = Column(Integer, default=50)

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
    academic_skill = Column(Integer, default=55)
    test_score = Column(Integer, default=55)
    drive = Column(Integer, default=50)
    loyalty = Column(Integer, default=50)
    volatility = Column(Integer, default=50)
    morale = Column(Integer, default=60)
    slump_timer = Column(Integer, default=0)
    archetype = Column(String, default="steady")

    # ---------- NEW PHYSICAL GROWTH ----------
    height_cm = Column(Integer, default=165)           # Current height (cm)
    height_potential = Column(Integer, default=180)    # Max possible height
    weight_kg = Column(Integer, default=72)            # Body mass for growth tuning
    is_two_way = Column(Boolean, default=False)
    secondary_position = Column(String, nullable=True)

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
    relationship_profile = relationship(
        "PlayerRelationship",
        back_populates="player",
        uselist=False,
        foreign_keys="PlayerRelationship.player_id",
    )
    skills = relationship(
        "PlayerSkill",
        back_populates="player",
        cascade="all, delete-orphan",
    )


# ============================================================
# 3b. PLAYER SKILLS TABLE
# ============================================================
class PlayerSkill(Base):
    __tablename__ = 'player_skills'
    __table_args__ = (
        Index('ix_player_skills_player_id', 'player_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    skill_key = Column(String, nullable=False)
    acquired_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)

    player = relationship("Player", back_populates="skills")


class PlayerMilestone(Base):
    __tablename__ = 'player_milestones'
    __table_args__ = (
        Index('ix_player_milestone_player_id', 'player_id'),
        Index('ix_player_milestone_key', 'milestone_key'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    milestone_key = Column(String, nullable=False)
    milestone_label = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    skill_key = Column(String, nullable=True)
    season_year = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    player = relationship("Player")


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
    weather_label = Column(String, nullable=True)
    weather_condition = Column(String, nullable=True)
    weather_precip = Column(String, nullable=True)
    weather_temperature_f = Column(Integer, nullable=True)
    weather_wind_speed = Column(Float, nullable=True)
    weather_wind_direction = Column(String, nullable=True)
    weather_summary = Column(Text, nullable=True)
    umpire_name = Column(String, nullable=True)
    umpire_description = Column(Text, nullable=True)
    umpire_zone_bias = Column(Float, nullable=True)
    umpire_home_bias = Column(Float, nullable=True)
    umpire_temperament = Column(Float, nullable=True)
    umpire_favored_home = Column(Integer, default=0)
    umpire_squeezed_home = Column(Integer, default=0)
    umpire_favored_away = Column(Integer, default=0)
    umpire_squeezed_away = Column(Integer, default=0)

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
    confidence = Column(Integer, default=0)

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
# 9. PLAYER RELATIONSHIP TABLE
# ============================================================
class PlayerRelationship(Base):
    __tablename__ = 'player_relationships'

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey('players.id'), unique=True)
    captain_id = Column(Integer, ForeignKey('players.id'), nullable=True)
    battery_partner_id = Column(Integer, ForeignKey('players.id'), nullable=True)
    rival_id = Column(Integer, ForeignKey('players.id'), nullable=True)

    captain_rel = Column(Integer, default=60)
    battery_rel = Column(Integer, default=55)
    rivalry_score = Column(Integer, default=45)

    last_captain_event_week = Column(Integer, default=0)
    last_rival_event_week = Column(Integer, default=0)

    player = relationship("Player", foreign_keys=[player_id], back_populates="relationship_profile")
    captain = relationship("Player", foreign_keys=[captain_id], post_update=True)
    battery_partner = relationship("Player", foreign_keys=[battery_partner_id], post_update=True)
    rival = relationship("Player", foreign_keys=[rival_id], post_update=True)


# ============================================================
# 10. COACH STRATEGY MODIFIERS
# ============================================================
class CoachStrategyMod(Base):
    __tablename__ = 'coach_strategy_mods'

    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(Integer, ForeignKey('schools.id'))
    effect_type = Column(String)
    games_remaining = Column(Integer, default=1)
    target_player_id = Column(Integer, ForeignKey('players.id'), nullable=True)
    payload = Column(Text, nullable=True)

    school = relationship("School")
    target_player = relationship("Player")


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
    active_player_id = Column(Integer, nullable=True)


# Aliases
Team = School
Performance = PlayerGameStats


# ============================================================
# DATABASE INITIALISATION
# ============================================================
def create_database():
    Base.metadata.create_all(engine)
    ensure_gamestate_schema()
    ensure_player_schema()
    ensure_player_skill_schema()
    ensure_player_milestone_schema()
    ensure_coach_schema()
    ensure_game_schema()
    ensure_game_stats_schema()
    ensure_game_schema()

    with session_scope() as session:
        if not session.query(GameState).first():
            print("Initialising Game State...")
            initial_state = GameState(
                current_day='MON',
                current_week=1,
                current_month=4,
                current_year=2024,
                active_player_id=None,
            )
            session.add(initial_state)

            session.commit()


if __name__ == "__main__":
    create_database()