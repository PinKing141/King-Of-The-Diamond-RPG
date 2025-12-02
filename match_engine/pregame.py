from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

from sqlalchemy.orm import Session

from database.setup_db import Player, School, GameState, PlayerRelationship
from game.coach_strategy import export_mod_descriptors
from game.player_progression import fetch_player_milestone_tags
from game.rng import get_rng
from match_engine.confidence import initialize_confidence
from match_engine.momentum import MomentumSystem, PresenceProfile, PresenceSystem


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


@dataclass
class UmpireProfile:
    """Defines the personality quirks for the plate umpire."""

    name: str
    zone_bias: float  # Positive squeezes the zone (more balls), negative expands
    home_bias: float  # Positive favors home pitchers, negative favors home batters
    temperament: float  # 0 (calm) -> 1 (fiery)
    description: str | None = None
    weight: float = 1.0


UMPIRE_PRESETS = [
    UmpireProfile(
        name="Ayako Tanaka",
        zone_bias=0.35,
        home_bias=-0.05,
        temperament=0.45,
        description="Tight zone that rewards patient hitters.",
        weight=1.1,
    ),
    UmpireProfile(
        name="Daisuke Mori",
        zone_bias=-0.25,
        home_bias=0.12,
        temperament=0.65,
        description="Generous corners, especially for the home ace.",
        weight=1.0,
    ),
    UmpireProfile(
        name="Haruto Sato",
        zone_bias=0.1,
        home_bias=0.0,
        temperament=0.3,
        description="Balanced caller who rarely loses his cool.",
        weight=0.9,
    ),
    UmpireProfile(
        name="Mika Fujimori",
        zone_bias=-0.05,
        home_bias=-0.08,
        temperament=0.8,
        description="Lets the home crowd sway borderline balls into base runners.",
        weight=0.8,
    ),
    UmpireProfile(
        name="Koji Nakamura",
        zone_bias=0.2,
        home_bias=0.15,
        temperament=0.55,
        description="Old-school strike zone with a subtle lean toward home pitchers.",
        weight=1.0,
    ),
]


class MatchState:
    """Container for all mutable state shared across the match engine."""

    def __init__(
        self,
        home_team,
        away_team,
        home_lineup,
        away_lineup,
        home_pitcher,
        away_pitcher,
        db_session,
        *,
        home_bench: Optional[Iterable[Player]] = None,
        away_bench: Optional[Iterable[Player]] = None,
    ):
        # Teams (Now Schools)
        self.home_team = home_team
        self.away_team = away_team
        
        # Lineups (List of Player objects)
        self.home_lineup = list(home_lineup)
        self.away_lineup = list(away_lineup)
        self.home_roster = list(self.home_lineup)
        self.away_roster = list(self.away_lineup)
        self.home_bench = list(home_bench or [])
        self.away_bench = list(away_bench or [])
        self.home_roster.extend(self.home_bench)
        self.away_roster.extend(self.away_bench)
        
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
        self.pitcher_presence = {}
        self.pitch_sequence_memory = {}
        self.times_through_order = {}
        self.batter_tell_tracker = {}
        self.argument_cooldowns = {}
        self.batters_eye_history: list[dict[str, object]] = []
        self.defensive_shift: str = "normal"
        self.ejections = []
        self.pinch_history = []
        self.pitching_changes = []
        self.last_change_reason = None
        self.player_milestones: dict[int, list[dict[str, object]]] = {}
        self.weather: WeatherState | None = None
        self.umpire: UmpireProfile | None = None
        self.umpire_mood: float = 0.0
        self.umpire_call_tilt: dict[int | None, dict[str, int]] = {}
        for team in (self.home_team, self.away_team):
            team_id = getattr(team, "id", None)
            if team_id is not None:
                self.umpire_call_tilt[team_id] = {"favored": 0, "squeezed": 0}
        self.umpire_plate_summary = {
            "offense": {"favored": 0, "squeezed": 0},
            "defense": {"favored": 0, "squeezed": 0},
        }
        self.team_rosters = {
            getattr(self.home_team, "id", None): self.home_roster,
            getattr(self.away_team, "id", None): self.away_roster,
        }
        self.bench_players = {
            getattr(self.home_team, "id", None): list(self.home_bench),
            getattr(self.away_team, "id", None): list(self.away_bench),
        }
        self.burned_bench = {
            getattr(self.home_team, "id", None): [],
            getattr(self.away_team, "id", None): [],
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

        self.momentum_system = MomentumSystem(
            getattr(self.home_team, "id", None),
            getattr(self.away_team, "id", None),
        )
        self.presence_system = PresenceSystem()
        self.pressure_index: float = 0.0
        self.aura_events: list[dict[str, object]] = []

    def configure_presence(self, profiles: Iterable[PresenceProfile]) -> None:
        self.presence_system.configure(profiles)

    def update_pressure_index(self) -> float:
        inning_factor = min(self.inning, 9) / 9.0
        score_gap = abs(self.home_score - self.away_score)
        gap_factor = 1.0 if score_gap == 0 else max(0.0, 1.0 - min(score_gap, 6) / 6.0)
        runner_weights = (0.15, 0.25, 0.35)
        runner_factor = 0.0
        for runner, weight in zip(self.runners, runner_weights):
            if runner:
                runner_factor += weight
        self.pressure_index = round(((inning_factor * 0.5) + (gap_factor * 0.3) + (runner_factor * 0.2)) * 10, 2)
        return self.pressure_index

    def pressure_penalty(self, player, role: str) -> float:
        if not player:
            return 0.0
        clutch = getattr(player, "clutch", 50) or 50
        if clutch >= 65:
            return 0.0
        pressure_scalar = max(0.0, self.pressure_index - 3.0) / 7.0
        clutch_gap = max(0.0, 65 - clutch) / 65.0
        penalty = round(pressure_scalar * clutch_gap, 3)
        return penalty if role.lower() in {"pitcher", "batter"} else 0.0

    def log_aura_event(self, payload: dict[str, object]) -> None:


    def _build_presence_profiles(state: MatchState) -> List[PresenceProfile]:
        profiles: List[PresenceProfile] = []

        def _profile_for_pitcher(pitcher, team_id: Optional[int]):
            if not pitcher or not getattr(pitcher, "id", None):
                return None
            return PresenceProfile(
                player_id=pitcher.id,
                team_id=team_id,
                role="ACE",
                trust_baseline=getattr(pitcher, "trust_baseline", 50) or 50,
            )

        def _profile_for_cleanup(lineup, team_id: Optional[int]):
            if len(lineup) < 4:
                return None
            cleanup = lineup[3]
            if not cleanup or not getattr(cleanup, "id", None):
                return None
            return PresenceProfile(
                player_id=cleanup.id,
                team_id=team_id,
                role="CLEANUP",
                trust_baseline=getattr(cleanup, "trust_baseline", 50) or 50,
            )

        home_id = getattr(state.home_team, "id", None)
        away_id = getattr(state.away_team, "id", None)

        for profile in (
            _profile_for_pitcher(state.home_pitcher, home_id),
            _profile_for_pitcher(state.away_pitcher, away_id),
            _profile_for_cleanup(state.home_lineup, home_id),
            _profile_for_cleanup(state.away_lineup, away_id),
        ):
            if profile:
                profiles.append(profile)

        return profiles
        self.aura_events.append(payload)

    def get_stats(self, p_id):
        if p_id not in self.stats:
            self.stats[p_id] = {
                "at_bats": 0, "hits": 0, "homeruns": 0, "rbi": 0,
                "strikeouts": 0, "walks": 0, "runs_allowed": 0,
                "strikeouts_pitched": 0, "innings_pitched": 0.0, "pitches": 0
            }
        return self.stats[p_id]

    def register_plate_appearance(self, pitcher_id: int | None, batter_id: int | None) -> int:
        if not pitcher_id or not batter_id:
            return 1
        tracker = self.times_through_order.setdefault(pitcher_id, {})
        tracker[batter_id] = tracker.get(batter_id, 0) + 1
        return tracker[batter_id]

    def set_player_milestones(self, mapping: dict[int, list[dict[str, object]]]):
        self.player_milestones = mapping or {}

    def player_has_milestone(self, player_id: Optional[int], milestone_key: str) -> bool:
        if not player_id or not milestone_key:
            return False
        entries = self.player_milestones.get(player_id, [])
        target = milestone_key.lower()
        return any((entry.get("key") or "").lower() == target for entry in entries)

    def get_player_milestone_labels(self, player_id: Optional[int]) -> list[str]:
        if not player_id:
            return []
        entries = self.player_milestones.get(player_id, [])
        return [str(entry.get("label") or entry.get("key")) for entry in entries]

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


def _tag_lineup_slots(lineup: Iterable[Player]) -> None:
    for idx, player in enumerate(lineup, start=1):
        if player is None:
            continue
        setattr(player, "_lineup_slot", idx)


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


def _roll_umpire_profile() -> UmpireProfile | None:
    if not UMPIRE_PRESETS:
        return None
    total = sum(profile.weight for profile in UMPIRE_PRESETS)
    roll = get_rng().random() * total
    running = 0.0
    for profile in UMPIRE_PRESETS:
        running += profile.weight
        if roll <= running:
            return profile
    return UMPIRE_PRESETS[-1]


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
    home_bench = [p for p in home_players if p not in home_lineup]
    _tag_lineup_slots(home_lineup)

    away_lineup = [p for p in away_players if p.is_starter][:9]
    if len(away_lineup) < 9:
        away_lineup = away_players[:9]
    away_bench = [p for p in away_players if p not in away_lineup]
    _tag_lineup_slots(away_lineup)
    
    # Select Pitcher
    # Try to find assigned 'ACE' or 'STARTER' pitcher role
    home_pitcher = next((p for p in home_players if p.position == 'Pitcher' and p.role == 'ACE'), None)
    if not home_pitcher: home_pitcher = next((p for p in home_players if p.position == 'Pitcher'), home_players[0])
    
    away_pitcher = next((p for p in away_players if p.position == 'Pitcher' and p.role == 'ACE'), None)
    if not away_pitcher: away_pitcher = next((p for p in away_players if p.position == 'Pitcher'), away_players[0])
    
    rivalry_info = _apply_rivalry_context(db_session, home_lineup, away_lineup)

    match_state = MatchState(
        home_team,
        away_team,
        home_lineup,
        away_lineup,
        home_pitcher,
        away_pitcher,
        db_session,
        home_bench=home_bench,
        away_bench=away_bench,
    )
    _attach_coach_modifiers(match_state)
    match_state.configure_presence(_build_presence_profiles(match_state))
    match_state.update_pressure_index()
    player_ids = [p.id for p in match_state.home_roster + match_state.away_roster if p and getattr(p, 'id', None)]
    match_state.set_player_milestones(fetch_player_milestone_tags(db_session, player_ids))
    match_state.weather = _roll_weather_state()
    if match_state.weather:
        description = match_state.weather.describe()
        match_state.log(f"Weather report: {description}")
        if match_state.weather.commentary_hint:
            match_state.log(match_state.weather.commentary_hint)
    match_state.umpire = _roll_umpire_profile()
    if match_state.umpire:
        summary = match_state.umpire.description or "Neutral strike zone in effect."
        match_state.log(f"Behind the plate: {match_state.umpire.name} — {summary}")
    if rivalry_info:
        match_state.hero_player_id = rivalry_info["hero_id"]
        match_state.hero_school_id = rivalry_info["hero_school_id"]
        match_state.hero_name = rivalry_info.get("hero_name")
        match_state.rival_player_id = rivalry_info["rival_id"]
        match_state.rival_name = rivalry_info.get("rival_name")
        match_state.rivalry_score = rivalry_info.get("rivalry_score")
        match_state.rivalry_delta = rivalry_info.get("delta", 0.0)
    return match_state