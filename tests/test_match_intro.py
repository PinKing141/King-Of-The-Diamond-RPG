from types import SimpleNamespace

from ui.match_intro import render_match_intro


class DummyWeather:
    def describe(self):
        return "Humid with light wind"


def _player(name: str, overall: int):
    return SimpleNamespace(name=name, overall=overall, last_name=name)


def test_render_match_intro_collects_core_lines():
    home = SimpleNamespace(name="Seiran", prestige=60, current_era="ASCENDING")
    away = SimpleNamespace(name="Kosei", prestige=35, current_era="REBUILDING")
    lineup_home = [_player("Ace", 78), _player("Slugger", 82)]
    lineup_away = [_player("Rival", 80)]
    logs = ["[Scouting Card] Kosei — Era: REBUILDING, Brass tier: 1. Star: Rival."]
    state = SimpleNamespace(
        home_team=home,
        away_team=away,
        home_lineup=lineup_home,
        away_lineup=lineup_away,
        tournament_name="Summer Koshien",
        hero_name="Akira",
        rival_name="Daigo",
        weather=DummyWeather(),
        umpire=SimpleNamespace(name="Ayako Tanaka", description="Tight zone"),
        logs=logs,
    )

    lines = render_match_intro(state, echo=False)

    assert any("Summer Koshien" in line for line in lines)
    assert any("Face-off" in line for line in lines)
    assert any("Seiran" in line for line in lines)
    assert any("Kosei" in line for line in lines)
    assert any(line.startswith("[Scouting Card]") for line in lines)
