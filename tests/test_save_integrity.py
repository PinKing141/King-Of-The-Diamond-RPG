import os
import sqlite3
from unittest.mock import patch

import pytest

from game import save_manager


@pytest.fixture
def save_environment(tmp_path, monkeypatch):
    """Sets up a temporary directory for DB and saves."""
    db_path = tmp_path / "active_game.db"
    user_data_dir = tmp_path / "saves"
    user_data_dir.mkdir()

    # Redirect paths in the module
    monkeypatch.setattr("game.save_manager.DB_PATH", str(db_path))
    monkeypatch.setattr("game.save_manager.USER_DATA_DIR", str(user_data_dir))

    return db_path, user_data_dir


def create_dummy_db(path, week=1, player_name="Test"):
    """Helper to create a valid SQLite DB with minimal schema."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE gamestate (id INTEGER PRIMARY KEY, current_week INTEGER, current_year INTEGER, last_error_summary TEXT, last_coach_order_result TEXT, last_telemetry_blob TEXT)"
    )
    conn.execute("INSERT INTO gamestate (current_week, current_year) VALUES (?, 2024)", (week,))
    conn.execute("CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO players (name) VALUES (?)", (player_name,))
    conn.commit()
    conn.close()


def test_save_game_creates_file(save_environment):
    db_path, save_dir = save_environment
    create_dummy_db(db_path)

    success, msg = save_manager.save_game(1)

    assert success
    assert "saved" in msg.lower()
    assert (save_dir / "save_slot_1.db").exists()


def test_load_game_restores_state(save_environment, monkeypatch):
    db_path, save_dir = save_environment

    create_dummy_db(db_path, week=5, player_name="Original")
    save_manager.save_game(1)

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE gamestate SET current_week = 99")
    conn.execute("UPDATE players SET name = 'Corrupted'")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(db_path)
    curr = conn.execute("SELECT current_week FROM gamestate").fetchone()[0]
    conn.close()
    assert curr == 99

    with patch("game.save_manager.create_database"):
        success, msg = save_manager.load_game(1)

    assert success

    conn = sqlite3.connect(db_path)
    restored_week = conn.execute("SELECT current_week FROM gamestate").fetchone()[0]
    restored_name = conn.execute("SELECT name FROM players").fetchone()[0]
    conn.close()

    assert restored_week == 5
    assert restored_name == "Original"


def test_load_fails_on_missing_slot(save_environment):
    success, msg = save_manager.load_game(99)
    assert not success
    assert "not found" in msg.lower()
