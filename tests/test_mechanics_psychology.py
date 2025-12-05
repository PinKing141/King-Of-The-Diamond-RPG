from types import SimpleNamespace

from game.mechanics import get_or_create_profile, mechanics_adjustment_for_pitch
from match_engine.pitch_logic import PitchResult
from match_engine.psychology import PsychologyEngine


class DummyState(SimpleNamespace):
    def __init__(self):
        super().__init__()
        self.pitcher_mechanics = {}
        self.logs = []


def _sample_pitcher():
    return SimpleNamespace(
        id=42,
        last_name="Aoki",
        arm_slot="Three-Quarters",
        stamina=68,
        aggression=62,
        height_inches=75,
    )


def test_mechanics_profile_is_cached():
    state = DummyState()
    pitcher = _sample_pitcher()
    profile_first = get_or_create_profile(state, pitcher)
    profile_second = get_or_create_profile(state, pitcher)
    assert profile_first is profile_second
    adjustment = mechanics_adjustment_for_pitch(
        profile_first,
        {"family": "Fastball", "plane": "ride"},
        location="Zone",
    )
    assert isinstance(adjustment.velocity_bonus, float)
    assert adjustment.movement_scalar > 0.5


def test_psychology_engine_tracks_pitch_and_plate_outcome():
    state = DummyState()
    engine = PsychologyEngine(state)
    pitch = PitchResult("4-Seam Fastball", "Zone", "Strike", "Swinging Miss", 95)
    engine.record_pitch(7, 11, pitch, leverage=1.4)
    snapshot = engine.pitcher_modifiers(7)
    assert snapshot.control_bonus > 0
    plate = SimpleNamespace(pitcher_id=7, batter_id=11, result_type="strikeout", drama_level=2)
    engine.record_plate_outcome(plate)
    updated = engine.pitcher_modifiers(7)
    assert updated.focus >= snapshot.focus
    batter_snapshot = engine.batter_modifiers(11)
    assert batter_snapshot.eye_scalar <= 1.0
