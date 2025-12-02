import pytest

from api_bridge import (
    ApiError,
    MAX_PITCHES,
    PITCH_SELECTION_POOL,
    _sanitize_pitch_selection,
    _serialize_training_details,
    _validate_schedule_grid,
)


def test_sanitize_pitch_selection_filters_invalid_and_limits_count():
    valid = list(PITCH_SELECTION_POOL)[: MAX_PITCHES + 2]
    payload = [valid[0], "Fake Pitch", valid[1], valid[1], valid[2], valid[3], valid[4]]
    result = _sanitize_pitch_selection(payload)
    assert len(result) == min(MAX_PITCHES, len(set(valid[: MAX_PITCHES + 1])))
    assert "Fake Pitch" not in result
    assert result[0] == valid[0]


def test_validate_schedule_grid_requires_7x3_grid():
    base_schedule = [[None, None, None] for _ in range(7)]
    normalized = _validate_schedule_grid(base_schedule)
    assert len(normalized) == 7
    assert all(len(day) == 3 for day in normalized)

    with pytest.raises(ApiError):
        _validate_schedule_grid([[None, None, None] for _ in range(6)])
    with pytest.raises(ApiError):
        _validate_schedule_grid([[None, None] for _ in range(7)])


def test_serialize_training_details_handles_nested_structures():
    class Dummy:
        def __str__(self):
            return "Dummy()"

    details = {
        "int": 5,
        "list": [1, Dummy()],
        "dict": {"nested": Dummy()},
        "obj": Dummy(),
    }
    serialized = _serialize_training_details(details)
    assert serialized["int"] == 5
    assert isinstance(serialized["obj"], str)
    assert serialized["list"][1] == "Dummy()"
    assert serialized["dict"]["nested"] == "Dummy()"
