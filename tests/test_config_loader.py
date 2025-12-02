import json

from game.config_loader import ConfigLoader


def test_config_loader_reads_sections(tmp_path):
    config_path = tmp_path / "balancing.json"
    payload = {
        "actions": {
            "costs": {"rest": -20},
            "metadata": {"rest": {"short": "CHILL"}},
        }
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    ConfigLoader.configure(path=str(config_path))
    try:
        actions = ConfigLoader.get_section("actions")
        assert actions["costs"]["rest"] == -20
        assert ConfigLoader.get("actions", "missing", default={}) == {}
    finally:
        ConfigLoader.configure(path=None)
