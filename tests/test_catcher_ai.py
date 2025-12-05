import sys
from types import ModuleType

_ORIGINAL_MODULES = {}
for name in ("match_engine", "match_engine.pitch_logic", "match_engine.pitch_definitions", "match_engine.states"):
    if name in sys.modules:
        _ORIGINAL_MODULES[name] = sys.modules[name]

stub_package = ModuleType("match_engine")
sys.modules["match_engine"] = stub_package

dummy_pitch_logic = ModuleType("match_engine.pitch_logic")
dummy_pitch_logic.describe_batter_tells = lambda state, batter: []
dummy_pitch_logic.get_arsenal = lambda pitcher_id: []
dummy_pitch_logic.get_last_pitch_call = lambda state, pitcher_id, batter_id: None
sys.modules["match_engine.pitch_logic"] = dummy_pitch_logic
stub_package.pitch_logic = dummy_pitch_logic

dummy_pitch_defs = ModuleType("match_engine.pitch_definitions")
dummy_pitch_defs.PITCH_TYPES = {}
sys.modules["match_engine.pitch_definitions"] = dummy_pitch_defs
stub_package.pitch_definitions = dummy_pitch_defs

dummy_states = ModuleType("match_engine.states")
sys.modules["match_engine.states"] = dummy_states
stub_package.states = dummy_states

from game import catcher_ai

for name in ("match_engine.states", "match_engine.pitch_definitions", "match_engine.pitch_logic", "match_engine"):
    if name in _ORIGINAL_MODULES:
        sys.modules[name] = _ORIGINAL_MODULES[name]
    else:
        sys.modules.pop(name, None)


def test_synergy_rewards_velocity_separation():
    bonus, tag = catcher_ai._calculate_synergy("4-Seam Fastball", "Changeup")
    assert bonus > 0
    assert "synergy" in tag


def test_synergy_penalizes_repeating_pitch():
    bonus, tag = catcher_ai._calculate_synergy("Slider", "Slider")
    assert bonus < 0
    assert "same look" in tag


def test_fatigue_guard_penalizes_high_cost_pitch_when_tired():
    penalty, reason = catcher_ai._fatigue_guard("Splitter", 8)
    assert penalty > 0
    assert "arm saver" in reason
