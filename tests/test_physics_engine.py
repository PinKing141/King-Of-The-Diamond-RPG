from __future__ import annotations

from types import SimpleNamespace

from match_engine.pitch_logic import resolve_pitch
from match_engine.ball_in_play import resolve_contact


class PitchTestState:
    def __init__(self):
        self.balls = 0
        self.strikes = 0
        self.pitch_counts = {}
        self.weather = None
        self.pitcher_presence = {}
        self.pitch_sequence_memory = {}
        self.batter_tell_tracker = {}
        self.runners = [None, None, None]
        self.top_bottom = "Top"
        self.home_team = SimpleNamespace(id=1, name="Home")
        self.away_team = SimpleNamespace(id=2, name="Away")
        self.momentum_system = SimpleNamespace(get_multiplier=lambda _: 1.0)
        self.logs = []
        self.umpire_mood = 0.0
        self.umpire = None
        self.argument_cooldowns = {}
        self.umpire_plate_summary = {
            "offense": {"favored": 0, "squeezed": 0},
            "defense": {"favored": 0, "squeezed": 0},
        }
        self.umpire_call_tilt = {}
        self.pitcher_diagnostics = {}
        self.commentary_memory = set()
        self.batters_eye_history = []
        self.pressure_index = 0.0
        self.confidence_map = {}
        self.home_lineup = [SimpleNamespace(position="Catcher")]
        self.away_lineup = [SimpleNamespace(position="Catcher")]

    def update_pressure_index(self):
        return 0.0

    def pressure_penalty(self, player, role):  # noqa: ARG002
        return 0.0

    def reset_count(self):
        self.balls = 0
        self.strikes = 0


def _make_pitcher(pid: int, velocity: int, stamina: int = 80):
    return SimpleNamespace(
        id=pid,
        name=f"Pitcher{pid}",
        position="Pitcher",
        velocity=velocity,
        control=70,
        movement=60,
        stamina=stamina,
        trust_baseline=60,
        team_id=1,
        arm_slot="Three-Quarters",
    )


def _make_batter(power: int, contact: int = 70):
    return SimpleNamespace(
        id=500 + power,
        name="Slugger",
        position="First Base",
        contact=contact,
        power=power,
        discipline=70,
        eye=70,
        team_id=2,
        speed=55,
    )


def _resolve_simple_pitch(pitcher, batter, *, pitch_count=0):
    state = PitchTestState()
    state.pitch_counts[pitcher.id] = pitch_count
    state.confidence_map = {pitcher.id: 0, batter.id: 0}
    return resolve_pitch(pitcher, batter, state, batter_action="Swing")


def test_high_velocity_pitch_registers_higher_velocity():
    fast_pitcher = _make_pitcher(1, 160)
    slow_pitcher = _make_pitcher(2, 120)
    batter = _make_batter(power=60)

    fast_result = _resolve_simple_pitch(fast_pitcher, batter)
    slow_result = _resolve_simple_pitch(slow_pitcher, batter)

    assert fast_result.velocity > slow_result.velocity


def test_fatigue_penalizes_pitch_quality():
    pitcher = _make_pitcher(3, 150)
    batter = _make_batter(power=55)

    fresh = _resolve_simple_pitch(pitcher, batter, pitch_count=20)
    fatigued = _resolve_simple_pitch(pitcher, batter, pitch_count=110)

    assert fatigued.velocity < fresh.velocity


def test_power_batter_creates_stronger_contact():
    state = PitchTestState()
    state.top_bottom = "Bot"
    state.home_team.id = 2  # ensure defense is not user-controlled
    pitcher = _make_pitcher(10, 130)
    power_batter = _make_batter(power=90)
    contact_batter = _make_batter(power=50, contact=90)

    power_result = resolve_contact(95, power_batter, pitcher, state, power_mod=10)
    contact_result = resolve_contact(95, contact_batter, pitcher, state, power_mod=10)

    hit_values = {"HR": 4, "3B": 3, "2B": 2, "1B": 1, "Out": 0}
    assert hit_values[power_result.hit_type] >= hit_values[contact_result.hit_type]
