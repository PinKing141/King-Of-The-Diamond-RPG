from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.orm import Session

from database.setup_db import Player, School, GameState, PlayerRelationship
from game.coach_strategy import export_mod_descriptors
from game.rng import get_rng
from match_engine.confidence import initialize_confidence


@dataclass
class WeatherState:
    """Represents the shared weather context for the entire matchup."""

    label: str
    condition: str
    precipitation: str
    temperature_f: int
    wind_speed_mph: float
    wind_direction: str
    carry_modifier: float
    error_modifier: float
    wild_pitch_modifier: float
    commentary_hint: str | None = None

    def describe(self) -> str:
        base = f"{self.label} ({self.temperature_f}°F, {self.wind_speed_mph:.1f} mph {self.wind_direction})"
        if self.precipitation != "none":
            base += f" - {self.precipitation.title()}"
        return base


WIND_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

WEATHER_PRESETS = [
    {
        "label": "Crisp & Calm",
        "condition": "clear",
        "precipitation": "none",
        "temp_range": (58, 70),
        "wind_range": (0.0, 5.0),
        "carry_modifier": 0.05,
        "error_modifier": -0.02,
        "wild_pitch_modifier": -0.03,
        "weight": 0.25,
        "commentary": "Perfect baseball weather with just a light breeze.",
    },
    {
        "label": "Humid Haze",
        "condition": "muggy",
        "precipitation": "none",
        "temp_range": (72, 82),
        "wind_range": (2.0, 8.0),
        "carry_modifier": 0.02,
        "error_modifier": 0.0,
        "wild_pitch_modifier": 0.01,
        "weight": 0.2,
        "commentary": "Heavy air could make the ball feel a little heavier off the bat.",
    },
    {
        "label": "Gusty Crosswinds",
        "condition": "windy",
        "precipitation": "none",
        "temp_range": (60, 75),
        "wind_range": (10.0, 18.0),
        "carry_modifier": -0.03,
        "error_modifier": 0.03,
        "wild_pitch_modifier": 0.04,
        "weight": 0.18,
        "commentary": "Crosswinds could wreak havoc on lofted balls and command alike.",
    },
    {
        "label": "Light Drizzle",
        "condition": "rain",
        "precipitation": "drizzle",
        "temp_range": (55, 68),
        "wind_range": (4.0, 12.0),
        "carry_modifier": -0.04,
        "error_modifier": 0.06,
        "wild_pitch_modifier": 0.07,
        "weight": 0.17,
        "commentary": "Slick conditions may test everyone's grip.",
    },
    {
        "label": "Steady Rain",
        "condition": "rain",
        "precipitation": "steady",
        "temp_range": (52, 65),
        "wind_range": (6.0, 15.0),
        "carry_modifier": -0.08,
        "error_modifier": 0.12,
        "wild_pitch_modifier": 0.12,
        "weight": 0.12,
        "commentary": "Field crews are watching puddles; expect defensive miscues.",
    },
    {
        "label": "Hot & Thin Air",
        "condition": "heat",
        "precipitation": "none",
        "temp_range": (85, 96),
        "wind_range": (3.0, 10.0),
        "carry_modifier": 0.09,
        "error_modifier": 0.02,
        "wild_pitch_modifier": 0.03,
        "weight": 0.08,
        "commentary": "Ball should really fly today but stamina will be a concern.",
    },
]


class MatchState:
    """Container for all mutable state shared across the match engine."""

    def __init__(self, home_team, away_team, home_lineup, away_lineup, home_pitcher, away_pitcher, db_session):
        # Teams (Now Schools)
        self.home_team = home_team
        self.away_team = away_team
        
        # Lineups (List of Player objects)
        self.home_lineup = list(home_lineup)
        self.away_lineup = list(away_lineup)
        self.home_roster = list(self.home_lineup)
        self.away_roster = list(self.away_lineup)
        
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

        # Shared session for writing back results/injuries
        self.db_session = db_session

        # Runtime trackers for enhanced commentary cues
        self.pitcher_diagnostics = {}
        self.team_mods = {}
        self.hero_player_id = None
        self.hero_school_id = None
        self.hero_name = None
        self.rival_player_id = None
        self.rival_name = None
        self.rivalry_score = None
        self.rivalry_delta = 0.0
        self.commentary_memory = set()
        self.pitcher_stress = {}
        self.catcher_settle_log = {}
        self.rally_tracker = {}
        self.slump_boost = {}
        self.confidence_events = []
        self.confidence_story = {}
        self.argument_cooldowns = {}
        self.weather: WeatherState | None = None
        self.team_rosters = {
            getattr(self.home_team, "id", None): self.home_roster,
            getattr(self.away_team, "id", None): self.away_roster,
        }
        self.player_lookup = {}
        for player in self.home_roster + self.away_roster:
            if player:
                self.player_lookup[player.id] = player
        if home_pitcher:
            self.player_lookup.setdefault(home_pitcher.id, home_pitcher)
        if away_pitcher:
            self.player_lookup.setdefault(away_pitcher.id, away_pitcher)
        self.player_team_map = {}
        for player in self.home_roster:
            if player:
                self.player_team_map[player.id] = self.home_team.id
        for player in self.away_roster:
            if player:
                self.player_team_map[player.id] = self.away_team.id
        initialize_confidence(self)

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

def _apply_rivalry_context(db_session: Session, home_lineup, away_lineup):
    state = db_session.query(GameState).first()
    if not state or not state.active_player_id:
        return None

    rel = db_session.query(PlayerRelationship).filter_by(player_id=state.active_player_id).one_or_none()
    if not rel or not rel.rival_id:
        return None

    everyone = home_lineup + away_lineup
    hero = next((p for p in everyone if p.id == state.active_player_id), None)
    rival = next((p for p in everyone if p.id == rel.rival_id), None)
    if not hero or not rival:
        return None

    delta = ((rel.rivalry_score or 45) - 45) / 6.0
    hero.clutch = max(25, min(99, (hero.clutch or 50) + delta))
    hero.mental = max(25, min(99, (hero.mental or 50) + (delta / 2)))
    def _display_name(player):
        return getattr(player, 'name', None) or getattr(player, 'last_name', None) or getattr(player, 'first_name', None) or "Player"
    return {
        "hero_id": hero.id,
        "hero_school_id": hero.school_id,
        "hero_name": _display_name(hero),
        "rival_id": rival.id,
        "rival_name": _display_name(rival),
        "rivalry_score": rel.rivalry_score or 45,
        "delta": delta,
    }


def _attach_coach_modifiers(state: MatchState):
    state.team_mods = {
        state.home_team.id: export_mod_descriptors(state.db_session, state.home_team.id),
        state.away_team.id: export_mod_descriptors(state.db_session, state.away_team.id),
    }


def _weighted_pick(options: Iterable[dict[str, Any]]):
    rng = get_rng()
    total = sum(opt.get("weight", 1.0) for opt in options)
    roll = rng.random() * total
    running = 0.0
    for option in options:
        running += option.get("weight", 1.0)
        if roll <= running:
            return option
    return options[-1]


def _roll_weather_state() -> WeatherState:
    preset = _weighted_pick(WEATHER_PRESETS)
    rng = get_rng()
    wind = rng.uniform(*preset["wind_range"])
    temp = rng.randint(*preset["temp_range"])
    direction = rng.choice(WIND_DIRECTIONS)
    return WeatherState(
        label=preset["label"],
        condition=preset["condition"],
        precipitation=preset["precipitation"],
        temperature_f=temp,
        wind_speed_mph=round(wind, 1),
        wind_direction=direction,
        carry_modifier=preset["carry_modifier"],
        error_modifier=preset["error_modifier"],
        wild_pitch_modifier=preset["wild_pitch_modifier"],
        commentary_hint=preset.get("commentary"),
    )


def prepare_match(home_id, away_id, db_session: Session):
    """
    Loads teams, builds lineups, selects pitchers.
    Returns a ready-to-use MatchState object.
    """
    # Use School model, use session.get()
    home_team = db_session.get(School, home_id)
    away_team = db_session.get(School, away_id)
    
    if not home_team or not away_team:
        print("Error: One of the teams could not be found.")
        return None

    # Corrected filtering: Use school_id instead of team_id
    home_players = db_session.query(Player).filter_by(school_id=home_id).order_by(Player.jersey_number).all()
    away_players = db_session.query(Player).filter_by(school_id=away_id).order_by(Player.jersey_number).all()
    
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
    
    rivalry_info = _apply_rivalry_context(db_session, home_lineup, away_lineup)

    match_state = MatchState(home_team, away_team, home_lineup, away_lineup, home_pitcher, away_pitcher, db_session)
    _attach_coach_modifiers(match_state)
    match_state.weather = _roll_weather_state()
    if match_state.weather:
        description = match_state.weather.describe()
        match_state.log(f"Weather report: {description}")
        if match_state.weather.commentary_hint:
            match_state.log(match_state.weather.commentary_hint)
    if rivalry_info:
        match_state.hero_player_id = rivalry_info["hero_id"]
        match_state.hero_school_id = rivalry_info["hero_school_id"]
        match_state.hero_name = rivalry_info.get("hero_name")
        match_state.rival_player_id = rivalry_info["rival_id"]
        match_state.rival_name = rivalry_info.get("rival_name")
        match_state.rivalry_score = rivalry_info.get("rivalry_score")
        match_state.rivalry_delta = rivalry_info.get("delta", 0.0)
    return match_state