from types import SimpleNamespace

from core.event_bus import EventBus
from match_engine.match_sim import MatchSimulation
from match_engine.states import EventType


class RivalCtx:
    def __init__(self, rival_batter_id: int, hero_pitcher_id: int):
        self.rival_batter_id = rival_batter_id
        self.hero_pitcher_id = hero_pitcher_id

    def is_rival_plate(self, batter_id):
        return batter_id == self.rival_batter_id

    def is_hero_pitching(self, pitcher_id):
        return pitcher_id == self.hero_pitcher_id


class StubMatchSim(MatchSimulation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed = 0

    def _execute_matchup(self):
        self.executed += 1
        return "resolved"


def _state(bus, ctx, batter_id: int, pitcher_id: int):
    batter = SimpleNamespace(id=batter_id, team_id=2, last_name="Rival")
    pitcher = SimpleNamespace(id=pitcher_id, team_id=1, last_name="Hero")
    return SimpleNamespace(
        inning=1,
        top_bottom="Top",
        home_score=0,
        away_score=0,
        balls=0,
        strikes=0,
        outs=0,
        home_team=SimpleNamespace(id=1, name="Home"),
        away_team=SimpleNamespace(id=2, name="Away"),
        home_lineup=[batter],
        away_lineup=[batter],
        home_pitcher=pitcher,
        away_pitcher=pitcher,
        get_stats=lambda _pid: {},
        rival_match_context=ctx,
        hero_name="Hero",
        rival_name="Rival",
        commentary_memory=set(),
        logs=[],
        player_lookup={batter_id: batter, pitcher_id: pitcher},
    )


def test_rival_cut_in_emits_and_pauses_once():
    bus = EventBus()
    events = []
    bus.subscribe(EventType.RIVAL_CUT_IN.value, lambda payload: events.append(payload))

    ctx = RivalCtx(rival_batter_id=22, hero_pitcher_id=10)
    state = _state(bus, ctx, batter_id=22, pitcher_id=10)

    sim = StubMatchSim(state, bus=bus)

    # First step triggers cut-in and pauses match execution
    assert sim.step() is None
    assert len(events) == 1
    assert events[0]["batter_id"] == 22
    assert sim.executed == 0

    # Second step should clear the hold; third executes the matchup
    assert sim.step() is None
    assert sim.step() == "resolved"
    assert sim.executed == 1

    # No duplicate cut-in once memoized
    assert len(events) == 1
