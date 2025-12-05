from types import SimpleNamespace

from game import talent_tree


def test_splitter_requires_changeup_path_and_metrics():
    player = SimpleNamespace(
        ability_points=5,
        control=62,
        stamina=55,
        movement=58,
        velocity=70,
        determination=72,
        power=80,
        height_cm=186,
        discipline=65,
    )
    assert not talent_tree.can_unlock_talent(player, "pitch_splitter", owned_nodes=set())
    owned = {"pitch_changeup"}
    assert talent_tree.can_unlock_talent(player, "pitch_splitter", owned_nodes=owned)


def test_slider_needs_parent_and_points():
    player = SimpleNamespace(
        ability_points=0,
        control=60,
        stamina=50,
        movement=60,
        velocity=65,
        determination=60,
        power=60,
        height_cm=180,
        discipline=60,
    )
    assert not talent_tree.can_unlock_talent(player, "pitch_slider", owned_nodes={"pitch_four_seam"})
    player.ability_points = 3
    assert talent_tree.can_unlock_talent(player, "pitch_slider", owned_nodes={"pitch_four_seam"})
    assert not talent_tree.can_unlock_talent(player, "pitch_slider", owned_nodes=set())
