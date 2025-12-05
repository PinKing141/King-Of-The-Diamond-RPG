import json
from types import SimpleNamespace

import pytest

from game.config_loader import ConfigLoader
from match_engine import controller as controller_module
from match_engine.controller import MatchController
from match_engine.scoreboard import Scoreboard
from match_engine.telemetry import ensure_collector, flush_telemetry, describe_action, get_actions_metadata
from match_engine.match_sim import PlayOutcome
from match_engine.states import MatchState
from match_engine.commentary import set_commentary_enabled
from match_engine import confidence as confidence_module


@pytest.fixture(autouse=True)
def disable_commentary():
    set_commentary_enabled(False)
    yield
    set_commentary_enabled(True)


@pytest.fixture
def config_payload(tmp_path):
    data = {
        "actions": {
            "metadata": {
                "rest": {"short": "RST", "desc": "Recover"},
                "study": {"short": "STDY", "desc": "Books"},
            }
        }
    }
    config_path = tmp_path / "balancing.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")
    ConfigLoader.configure(path=str(config_path))
    yield data
    ConfigLoader.configure(path=None)


@pytest.fixture
def stub_simulation(monkeypatch):
    class _StubSimulation:
        def __init__(self, state, **_):
            self.state = state
            self.loop_state = MatchState.WAITING_FOR_PITCH
            self.awaiting_player_choice = False
            self._trust_buffer = {}

        def step(self):
            return None

        def pop_trust_buffer(self):
            buffer = self._trust_buffer
            self._trust_buffer = {}
            return buffer

    monkeypatch.setattr(controller_module, "MatchSimulation", _StubSimulation)


class _DummyTeam:
    def __init__(self, name: str, team_id: int):
        self.name = name
        self.id = team_id


class _DummyState:
    def __init__(self):
        self.inning = 9
        self.top_bottom = "Top"
        self.home_score = 0
        self.away_score = 0
        self.home_team = _DummyTeam("Home", 2)
        self.away_team = _DummyTeam("Away", 1)
        self.home_lineup = [SimpleNamespace(id=11, name="Hitter", position="1B")]
        self.away_lineup = [SimpleNamespace(id=21, name="Slugger", position="CF")]
        self.home_pitcher = SimpleNamespace(id=101)
        self.away_pitcher = SimpleNamespace(id=201)
        self.balls = 0
        self.strikes = 0
        self.outs = 0
        self.event_bus = None
        self.weather = None
        self.logs = []
        self.confidence_story = None
        self.player_lookup = {}
        self.rival_match_context = None
        self.hero_school_id = None
        self.rival_postgame = None

    def clear_bases(self):
        self.bases_cleared = getattr(self, "bases_cleared", 0) + 1

    def get_player_milestone_labels(self, _):
        return []

    def get_stats(self, _):
        return {"hits": 0}


@pytest.fixture
def controller_stub(stub_simulation, config_payload):
    state = _DummyState()
    scoreboard = Scoreboard()
    ctrl = MatchController(state, scoreboard)
    return ctrl


def test_metadata_helpers_use_config_loader(config_payload):
    metadata = get_actions_metadata()
    assert metadata["rest"]["short"] == "RST"
    action = describe_action("study")
    assert action["desc"] == "Books"


def test_inning_telemetry_marks_skipped_bottom(controller_stub, config_payload):
    ctrl = controller_stub
    ctrl.state.inning = 9
    ctrl._current_inning_runs = {"Top": 2, "Bot": 0}
    ctrl._record_inning(skip_bottom=True)
    last_event = ctrl.telemetry.events[-1]
    assert last_event["type"] == "inning_complete"
    assert last_event["payload"]["skipped_bottom"] is True


def test_walkoff_emits_event_and_metadata(controller_stub, config_payload):
    ctrl = controller_stub
    ctrl.state.top_bottom = "Bot"
    ctrl.state.home_score = 3
    ctrl.state.away_score = 2
    ctrl.state.latest_play_detail = {"runs_scored": 1, "description": "Walkoff single"}
    ctrl.state.umpire_call_tilt = {ctrl.state.home_team.id: {"favored": 2, "squeezed": 0}}
    ctrl._current_inning_runs = {"Top": 0, "Bot": 0}
    outcome = PlayOutcome(
        inning=9,
        half="Bot",
        batter_id=None,
        pitcher_id=None,
        outs_recorded=1,
        runs_scored=1,
        description="Walkoff single",
        result_type="hit",
        half_complete=True,
        drama_level=3,
        batting_team="home",
        fielding_team="away",
    )
    result = ctrl._apply_outcome(outcome)
    assert result is not None  # Game should finish
    walkoffs = [entry for entry in ctrl.telemetry.events if entry["type"] == "walkoff"]
    assert walkoffs, "Expected walkoff telemetry entry"
    assert walkoffs[0]["payload"]["runs_scored"] == 1
    game_over = [entry for entry in ctrl.telemetry.events if entry["type"] == "game_over"]
    assert game_over, "Expected game_over telemetry entry"
    assert game_over[0]["payload"]["actions"] == config_payload["actions"]["metadata"]
    tilt = [entry for entry in ctrl.telemetry.events if entry["type"] == "umpire_tilt"]
    assert tilt and tilt[0]["payload"]["tilt"]


def test_confidence_adjustment_records_event():
    player = SimpleNamespace(
        id=55,
        name="Slugger",
        loyalty=60,
        volatility=40,
        slump_timer=0,
        position="cf",
        team_id=1,
    )
    state = SimpleNamespace(
        confidence_map={55: 0},
        player_team_map={55: 1},
        player_lookup={55: player},
        team_rosters={1: [player]},
        home_team=SimpleNamespace(id=1),
        away_team=SimpleNamespace(id=2),
        home_pitcher=None,
        away_pitcher=None,
        confidence_story={},
        confidence_events=[],
        rally_tracker=None,
        slump_boost=None,
        catcher_settle_log=None,
        pitcher_stress=None,
        top_bottom="Top",
        runners=[],
        inning=5,
        event_bus=None,
    )
    confidence_module.adjust_confidence(state, 55, 12, reason="clutch_hit")
    swings = [entry for entry in state.telemetry.events if entry["type"] == "confidence_swing"]
    assert swings and swings[0]["payload"]["player_id"] == 55


def test_flush_writes_to_all_targets(tmp_path):
    class DummyBus:
        def __init__(self):
            self.messages = []

        def publish(self, name, payload):
            self.messages.append((name, payload))

    class DummyQuery:
        def __init__(self, row):
            self.row = row

        def first(self):
            return self.row

    class DummySession:
        def __init__(self):
            self.row = SimpleNamespace(last_telemetry_blob=None)

        def query(self, model):
            self.model = model
            return DummyQuery(self.row)

        def add(self, obj):
            self.added = obj

    state = SimpleNamespace(
        event_bus=DummyBus(),
        telemetry_output_path=str(tmp_path / "telemetry.json"),
        telemetry_store_in_db=True,
        db_session=DummySession(),
    )
    collector = ensure_collector(state)
    collector.record_event("test", {"hello": 1})

    flush_telemetry(state)

    assert state.event_bus.messages and state.event_bus.messages[0][0] == "TELEMETRY_READY"
    file_path = tmp_path / "telemetry.json"
    assert json.loads(file_path.read_text(encoding="utf-8"))[0]["type"] == "test"
    assert state.db_session.row.last_telemetry_blob is not None
