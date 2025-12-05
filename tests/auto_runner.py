"""Automation harness that forces a minigame clutch payload and validates telemetry wiring."""
from __future__ import annotations

import builtins
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from core.event_bus import EventBus
from database.setup_db import School, get_session
from game.analytics import TELEMETRY_EVENT, initialise_analytics
from game.pitch_minigame import trigger_pitch_minigame
from match_engine.commentary import set_commentary_enabled
from match_engine.controller import GameResult, MatchController
from match_engine.match_sim import PlayOutcome
from match_engine.pregame import prepare_match
from match_engine.scoreboard import Scoreboard
from match_engine.states import MatchState as LoopState
from match_engine.telemetry import ensure_collector, flush_telemetry


class InputMock:
    """Context manager that mutes interactive prompts during the harness run."""

    def __init__(self, value: str = "\n") -> None:
        self.value = value
        self._original: Optional[Callable[..., str]] = None

    def __enter__(self):
        self._original = builtins.input
        builtins.input = lambda *_, **__: self.value
        return self

    def __exit__(self, exc_type, exc, tb):
        builtins.input = self._original  # type: ignore[arg-type]
        return False


class _StubSimulation:
    """Deterministic stand-in for MatchSimulation that completes one inning."""

    def __init__(self, state) -> None:
        self.state = state
        self.loop_state = LoopState.WAITING_FOR_PITCH
        self.awaiting_player_choice = False
        self._pending_halves: List[str] = ["Top", "Bot"]

    def step(self) -> Optional[PlayOutcome]:
        if not self._pending_halves:
            return None
        half = self._pending_halves.pop(0)
        self.state.top_bottom = half
        self.state.outs = 3
        inning = self.state.inning
        if half == "Top":
            runs = 0
            self.state.away_score += runs
            batting, fielding = "away", "home"
        else:
            runs = 1
            self.state.home_score += runs
            batting, fielding = "home", "away"
        return PlayOutcome(
            inning=inning,
            half=half,
            batter_id=None,
            pitcher_id=None,
            outs_recorded=3,
            runs_scored=runs,
            description="AutoRunner scripted half",
            result_type="scripted",
            half_complete=True,
            drama_level=1,
            batting_team=batting,
            fielding_team=fielding,
        )


def _select_schools(session) -> Tuple[School, School]:
    schools: Sequence[School] = session.query(School).order_by(School.id).limit(2).all()
    if len(schools) < 2:
        raise RuntimeError("Auto-runner requires at least two schools in the database.")
    return schools[0], schools[1]


def _build_clutch_payload(team: School, label: str) -> Dict[str, object]:
    result = trigger_pitch_minigame(
        inning=9,
        half="Bot",
        count="3-2",
        runners_on=3,
        score_diff=0,
        label=label,
        control_stat=85,
        fatigue_level=10,
        difficulty=0.42,
        auto_resolve=True,
    )
    context = result.context
    payload: Dict[str, object] = {
        "team_id": getattr(team, "id", None),
        "team_name": getattr(team, "name", "AutoRunner Home"),
        "team_side": "home",
        "quality": result.quality,
        "feedback": result.feedback,
        "deviation": result.deviation,
        "difficulty": result.difficulty,
        "target_window": result.target_window,
        "context": {
            "inning": context.inning,
            "half": context.half,
            "count": context.count,
            "runners_on": context.runners_on,
            "score_diff": context.score_diff,
            "label": context.label,
        },
    }
    if result.quality >= 0.9:
        payload["force_result"] = "strikeout"
    elif result.quality >= 0.8:
        payload["force_result"] = "strike"
    return payload


def _drive_until_inning_recorded(controller: MatchController, *, max_steps: int = 20) -> None:
    steps = 0
    while not controller.scoreboard.innings and steps < max_steps:
        outcome = controller.step()
        if isinstance(outcome, GameResult):
            break
        steps += 1


def run_auto_harness() -> bool:
    """Spin up analytics, drive one inning, and confirm telemetry hits the event bus."""

    set_commentary_enabled(False)
    session = get_session()
    try:
        home, away = _select_schools(session)
        payload = _build_clutch_payload(home, "Telemetry AutoRunner")
        state = prepare_match(home.id, away.id, session, clutch_pitch=payload)
        if not state:
            raise RuntimeError("prepare_match returned None.")

        bus = initialise_analytics(getattr(state, "event_bus", EventBus()), buffer_size=1)
        state.event_bus = bus
        ensure_collector(state)

        telemetry_events: List[Dict[str, object]] = []
        bus.subscribe(TELEMETRY_EVENT, lambda payload: telemetry_events.append(payload or {}))

        scoreboard = Scoreboard()
        controller = MatchController(state, scoreboard)
        controller.simulation = _StubSimulation(state)

        with InputMock():
            _drive_until_inning_recorded(controller)

        flush_telemetry(state)
        return bool(telemetry_events and telemetry_events[0].get("events"))
    finally:
        session.close()


def main() -> None:
    success = run_auto_harness()
    if success:
        print("Auto-runner captured telemetry successfully.")
    else:
        raise SystemExit("Auto-runner failed to observe telemetry events.")


if __name__ == "__main__":
    main()
