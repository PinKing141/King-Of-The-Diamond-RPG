import json
import sqlite3

from game import save_manager


def _write_slot(db_path, *, error_summary=None, order_result=None, telemetry_blob=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE gamestate (id INTEGER PRIMARY KEY, current_day TEXT, current_week INTEGER, current_month INTEGER, current_year INTEGER, last_error_summary TEXT, last_coach_order_result TEXT, last_telemetry_blob TEXT)"
    )
    conn.execute(
        "INSERT INTO gamestate (id, current_day, current_week, current_month, current_year, last_error_summary, last_coach_order_result, last_telemetry_blob) VALUES (1, 'MON', 5, 4, 2025, ?, ?, ?)",
        (json.dumps(error_summary), json.dumps(order_result), json.dumps(telemetry_blob)),
    )
    conn.commit()
    conn.close()


def test_get_save_slots_includes_metadata(monkeypatch, tmp_path):
    slot_path = tmp_path / "save_slot_1.db"
    error_summary = {"home": [{"tag": "SS", "rbis": 2}], "away": []}
    order_result = {
        "order": {"key": "run_50km", "description": "Run 50km"},
        "completed": True,
        "progress": {"value": 3, "target": 3},
        "reward_delta": {"trust": 4, "ability_points": 1},
    }
    _write_slot(slot_path, error_summary=error_summary, order_result=order_result)

    monkeypatch.setattr(save_manager, "USER_DATA_DIR", str(tmp_path))

    slots = save_manager.get_save_slots()
    assert len(slots) == 1
    metadata = slots[0]["metadata"]
    assert metadata["last_error_summary"]["home"][0]["tag"] == "SS"
    assert metadata["last_coach_order_result"]["completed"] is True
    assert "last_telemetry_blob" in metadata
    preview = slots[0]["preview"]
    assert preview
    assert "Coach Order" in preview
    assert "Errors" in preview
