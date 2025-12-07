from __future__ import annotations

from types import SimpleNamespace
import os
import sys
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine

# Ensure the project root is importable when running under pytest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.rng import seed_global_rng
from database import setup_db


@pytest.fixture(scope="function", autouse=True)
def isolate_database(tmp_path, monkeypatch):
    """Force each test to use an isolated SQLite file to avoid cross-test locks."""
    test_db_path = tmp_path / "test_koshien.db"
    test_db_url = f"sqlite:///{test_db_path}"

    test_engine = create_engine(test_db_url, connect_args={"timeout": 5})

    # Redirect the global engine/session factory used across the codebase
    monkeypatch.setattr(setup_db, "engine", test_engine)
    setup_db.SessionLocal.configure(bind=test_engine)

    # Initialize schema within the isolated database
    setup_db.create_database()

    yield

    test_engine.dispose()


@pytest.fixture(autouse=True)
def reseed_rng():
    seed_global_rng(1337)
    yield
    seed_global_rng(None)


@pytest.fixture(scope="function", autouse=True)
def stub_pykakasi(monkeypatch):
    """
    Prevent loading heavy pykakasi dictionaries during tests by stubbing the module and
    pre-existing imports.
    """
    mock_kks = MagicMock()
    mock_instance = MagicMock()
    mock_instance.convert.side_effect = lambda text: [{"hepburn": text}]
    mock_kks.kakasi.return_value = mock_instance

    monkeypatch.setitem(sys.modules, "pykakasi", mock_kks)

    if "world.coach_generation" in sys.modules:
        import world.coach_generation

        monkeypatch.setattr(world.coach_generation, "kks", mock_instance)

    if "database.populate_japan" in sys.modules:
        import database.populate_japan

        monkeypatch.setattr(database.populate_japan, "kks", mock_instance)


@pytest.fixture(autouse=True)
def stub_battery_negotiation(monkeypatch):
    from battery_system import battery_negotiation

    def _fake_call(*args, **kwargs):
        pitch = SimpleNamespace(pitch_name="4-Seam Fastball", break_level=40, quality=45)
        return SimpleNamespace(
            pitch=pitch,
            location="Zone",
            intent="Normal",
            shakes=0,
            trust=70,
            forced=False,
        )

    monkeypatch.setattr(battery_negotiation, "run_battery_negotiation", _fake_call)