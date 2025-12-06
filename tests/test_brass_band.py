from types import SimpleNamespace

from core.event_bus import EventBus

from match_engine.brass_band import BrassBand


def _mock_state(**overrides):
    base = {
        "home_team": SimpleNamespace(id=1, name="Home", prestige=10, current_era="RISE"),
        "away_team": SimpleNamespace(id=2, name="Away", prestige=10, current_era="RISE"),
        "player_lookup": {},
        "player_team_map": {},
        "logs": [],
        "event_bus": EventBus(),
        "tournament_name": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_brass_band_forces_koshien_support():
    state = _mock_state(tournament_name="Summer Koshien", home_team=SimpleNamespace(id=1, name="Home", prestige=5))

    band = BrassBand(state)

    assert band.support_tier == 3


def test_brass_band_walkup_announces_theme_for_home_side():
    player_id = 99
    player = SimpleNamespace(id=player_id, theme_song="Crimson Flash", last_name="Sato")
    state = _mock_state(
        home_team=SimpleNamespace(id=10, name="Noisy", prestige=70),
        player_lookup={player_id: player},
        player_team_map={player_id: 10},
        logs=[],
    )
    events = []
    state.event_bus.subscribe("COMMENTARY_LOG", lambda payload: events.append(payload))

    band = BrassBand(state)
    band.on_state_change({"state": "STATE_WINDUP", "batter_id": player_id})

    assert any("Crimson Flash" in entry for entry in state.logs)
    assert events, "Expected commentary event to fire"
    assert "Crimson Flash" in events[0]["text"]
