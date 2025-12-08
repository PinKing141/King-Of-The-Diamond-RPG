import sys

import pytest

from match_engine import resolver


class _DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        return None


def _inc_call(counter, key):
    counter[key] = counter.get(key, 0) + 1


def test_silent_path_avoids_stdout_hijack_and_passes_flag(monkeypatch):
    call_state = {}

    def fake_engine_run_match(*args, **kwargs):
        call_state["kwargs"] = kwargs
        return "winner"

    monkeypatch.setattr(resolver, "engine_run_match", fake_engine_run_match)
    monkeypatch.setattr(resolver, "session_scope", lambda: _DummySession())
    monkeypatch.setattr(resolver, "consume_strategy_mods", lambda *args, **kwargs: _inc_call(call_state, "consume_calls"))
    monkeypatch.setattr(resolver, "_fetch_latest_score", lambda *args, **kwargs: "1 - 0")

    before_stdout = sys.stdout

    home = type("Team", (), {"id": 1})()
    away = type("Team", (), {"id": 2})()

    winner, score = resolver._simulate_match(
        home,
        away,
        "Practice Match",
        silent=True,
        fast=False,
        persist_results=False,
    )

    assert winner == "winner"
    assert score == "1 - 0"
    assert call_state["kwargs"]["silent"] is True
    assert call_state["kwargs"]["auto_play_inputs"] is True
    assert sys.stdout is before_stdout, "sys.stdout should not be reassigned in silent mode"
    assert call_state.get("consume_calls") == 2, "strategy mods should be consumed for both teams"
