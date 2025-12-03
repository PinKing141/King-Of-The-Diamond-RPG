from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.rng import seed_global_rng


@pytest.fixture(autouse=True)
def reseed_rng():
    seed_global_rng(1337)
    yield
    seed_global_rng(None)


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