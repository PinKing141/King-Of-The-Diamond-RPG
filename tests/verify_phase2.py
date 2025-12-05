"""Quick stress test for the Phase 2 momentum system."""
from __future__ import annotations

import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.event_bus import EventBus
from match_engine.momentum import MomentumSystem, ZONE_THRESHOLD
from match_engine.states import EventType


def _publish_strikeout(bus: EventBus, *, half: str, fielding_side: str) -> None:
    payload = {
        "half": half,
        "fielding_team": fielding_side,
        "batting_team": "away" if fielding_side == "home" else "home",
    }
    bus.publish(EventType.STRIKEOUT.value, payload)


def _publish_homerun(bus: EventBus, *, batting_side: str) -> None:
    payload = {
        "half": "Top" if batting_side == "away" else "Bot",
        "batting_team": batting_side,
        "fielding_team": "home" if batting_side == "away" else "away",
        "hit_type": "HR",
        "double_play": False,
    }
    bus.publish(EventType.PLAY_RESULT.value, payload)


def run_stress_test() -> dict:
    bus = EventBus()
    shift_events: list[dict] = []
    bus.subscribe(EventType.MOMENTUM_SHIFT.value, lambda payload: shift_events.append(dict(payload)))

    system = MomentumSystem(home_team_id=101, away_team_id=202, bus=bus)

    for _ in range(3):
        _publish_strikeout(bus, half="Top", fielding_side="home")
    assert system.meter > 0, "Strikeouts should tilt the meter toward the defense."
    defensive_meter = system.meter

    _publish_homerun(bus, batting_side="away")
    assert system.meter < defensive_meter, "Home run should swing momentum toward the offense."
    assert defensive_meter - system.meter >= 4, "Home run swing should be material (>=4 points)."

    while system.meter > -ZONE_THRESHOLD:
        _publish_homerun(bus, batting_side="away")

    assert system.meter <= -ZONE_THRESHOLD, "Meter must enter the offensive zone (<= -10)."
    assert any(evt.get("team_side") == "away" for evt in shift_events), "Expected MOMENTUM_SHIFT for offense."

    return {
        "final_meter": system.meter,
        "shift_events": shift_events,
    }


if __name__ == "__main__":
    summary = run_stress_test()
    print("Phase 2 momentum stress test passed.")
    print(f"Final meter: {summary['final_meter']}")
    print(f"Shift events: {summary['shift_events']}")
