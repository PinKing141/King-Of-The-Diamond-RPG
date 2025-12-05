from world_sim import tournament_sim


def test_dialogue_library_contains_registered_ids():
    tournament_sim._DIALOGUE_LIBRARY.clear()
    tournament_sim._load_dialogues()
    missing = [
        dialogue_id
        for dialogue_id in sorted(tournament_sim.REGISTERED_DIALOGUE_IDS)
        if not tournament_sim._get_dialogue(dialogue_id)
    ]
    assert not missing, f"Missing dialogue entries: {missing}"


def test_unknown_dialogue_returns_none():
    tournament_sim._DIALOGUE_LIBRARY.clear()
    tournament_sim._load_dialogues()
    assert tournament_sim._get_dialogue("non_existent_dialogue_id") is None
