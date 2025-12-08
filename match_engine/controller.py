"""High-level orchestration for the match engine."""
from __future__ import annotations

from dataclasses import dataclass
import random
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence

from core.event_bus import EventBus
from core.io_interface import IOInterface

from .pregame import prepare_match
from .match_sim import MatchSimulation, MatchupContext, PlayOutcome
from .commentary import CommentaryListener, commentary_enabled, set_commentary_enabled
from .scoreboard import Scoreboard
from .manager_ai import manage_team_between_innings

from .telemetry import ensure_collector, flush_telemetry
from database.setup_db import Game, get_session, session_scope

from game.personnel.relationship_manager import seed_relationships
from core.services import SessionProvider, TempEffects
from match_engine.persistence import MatchPersistenceService
from .states import EventType, MatchState, InningHalf
from .batter_logic import AtBatStateMachine
from .input_system import HumanBatterInput, CpuBatterInput
from .momentum import MomentumSystem
from .states import PlayMode
from .brass_band import BrassBand

from battery_system.battery_trust import apply_trust_buffer
from game.mechanics.pitch_mastery import summarize_mastery_report, flush_pitch_xp
from game.coach_strategy import consume_strategy_mods

HALF_TOP = InningHalf.TOP.value
HALF_BOT = InningHalf.BOT.value


def _serialize_lineup(state, lineup: List[Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for idx, player in enumerate(lineup[:9], start=1):
        if player is None:
            continue
        player_id = getattr(player, "id", None)
        entries.append(
            {
                "slot": idx,
                "player_id": player_id,
                "name": getattr(player, "name", None)
                or getattr(player, "last_name", "Player"),
                "position": getattr(player, "position", "??"),
                "milestones": state.get_player_milestone_labels(player_id),
            }
        )
    return entries


def _emit_lineup_event(state) -> None:
    bus = getattr(state, "event_bus", None)
    if not bus:
        return
    payload = {
        "home": {
            "team_id": getattr(state.home_team, "id", None),
            "team_name": getattr(state.home_team, "name", "Home"),
            "lineup": _serialize_lineup(state, state.home_lineup),
        },
        "away": {
            "team_id": getattr(state.away_team, "id", None),
            "team_name": getattr(state.away_team, "name", "Away"),
            "lineup": _serialize_lineup(state, state.away_lineup),
        },
    }
    bus.publish("LINEUP_READY", payload)

def _rotate_lineup(lineup: List[Any]) -> List[Any]:
    if not lineup:
        return lineup
    return lineup[1:] + lineup[:1]

@dataclass
class MatchContext:
    """Lightweight snapshot describing pacing metadata."""

    inning: int
    half: str
    loop_state: MatchState = MatchState.WAITING_FOR_PITCH
    awaiting_input: bool = False
    last_outcome: Optional[PlayOutcome] = None


@dataclass
class GameResult:
    """Return type emitted when the controller finishes a game."""

    winner: Any


class MatchController:
    """Owns the paced match loop and delegates at-bats to MatchSimulation."""

    def __init__(
        self,
        state,
        scoreboard: Scoreboard,
        *,
        human_team_ids: Optional[Sequence[int]] = None,
        io: Optional[IOInterface] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.state = state
        self.scoreboard = scoreboard
        self.io = io
        self.rng = rng or getattr(state, "rng", random.Random())
        if io is not None:
            setattr(self.state, "io", io)
        setattr(self.state, "rng", self.rng)
        event_bus = getattr(state, "event_bus", None)
        self.bus: EventBus = event_bus if isinstance(event_bus, EventBus) else EventBus()
        state.event_bus = self.bus
        momentum = getattr(state, "momentum_system", None)
        if isinstance(momentum, MomentumSystem):
            momentum.attach_bus(self.bus)
        else:
            state.momentum_system = MomentumSystem(
                getattr(state.home_team, "id", None),
                getattr(state.away_team, "id", None),
                bus=self.bus,
            )
        if not getattr(state, "brass_band", None):
            state.brass_band = BrassBand(state, rng=self.rng)
        self._install_fielding_trust_map(state)
        self.simulation = MatchSimulation(
            state,
            bus=self.bus,
            human_team_ids=human_team_ids,
            rng=self.rng,
        )
        self.context = MatchContext(inning=state.inning, half=state.top_bottom)
        self._started = False
        self._needs_inning_setup = True
        self._current_inning_runs = {HALF_TOP: 0, HALF_BOT: 0}
        self._finished = False
        self._winner = None

    def _install_fielding_trust_map(self, state) -> None:
        """Precompute light fielding trust scalars from relationship seeds."""

        roster_map = getattr(state, "team_rosters", {}) or {}
        session = getattr(state, "db_session", None)
        if not session or not roster_map:
            state.fielding_trust_scalar = {}
            return
        trust: Dict[int, float] = {}
        for team_id, roster in roster_map.items():
            if not roster:
                continue
            totals = []
            for player in roster:
                try:
                    rel = seed_relationships(session, player)
                except Exception:
                    continue
                captain = getattr(rel, "captain_rel", 50) or 50
                battery = getattr(rel, "battery_rel", 50) or 50
                totals.append((captain + battery) / 2.0)
            if not totals:
                continue
            avg = sum(totals) / len(totals)
            # High trust trims errors slightly; low trust inflates them a touch.
            scalar = 1.0 - ((avg - 50.0) / 500.0)
            trust[team_id] = max(0.9, min(1.08, scalar))
        state.fielding_trust_scalar = trust

    def start_game(self):
        """Run the game to completion (legacy helper)."""

        while True:
            result = self.step()
            if isinstance(result, GameResult):
                return result.winner

    def step(self) -> GameResult | PlayOutcome | None:
        if self._finished:
            return GameResult(self._winner)

        if not self._started:
            self._start_match()
            return None

        if self._needs_inning_setup:
            self._prepare_inning()
            self._needs_inning_setup = False
            return None

        outcome = self.simulation.step()
        self.context.loop_state = self.simulation.loop_state
        self.context.awaiting_input = self.simulation.awaiting_player_choice
        if outcome is None:
            return None
        self.context.last_outcome = outcome
        self._maybe_update_play_mode(outcome)
        result = self._apply_outcome(outcome)
        return result or outcome

    def _start_match(self) -> None:
        self._started = True
        self._state_change(
            "MATCH_START",
            {
                "home_team_id": getattr(self.state.home_team, "id", None),
                "away_team_id": getattr(self.state.away_team, "id", None),
                "home_team_name": getattr(self.state.home_team, "name", "Home"),
                "away_team_name": getattr(self.state.away_team, "name", "Away"),
            },
        )
        _emit_lineup_event(self.state)

    def _prepare_inning(self) -> None:
        manage_team_between_innings(self.state, "Home", io=self.io)
        manage_team_between_innings(self.state, "Away", io=self.io)
        self._state_change(
            "INNING_READY",
            {"inning": self.state.inning, "half": HALF_TOP},
        )
        self._current_inning_runs = {HALF_TOP: 0, HALF_BOT: 0}
        self._begin_half(HALF_TOP)

    def _begin_half(self, half: str) -> None:
        self.state.top_bottom = half
        self.state.outs = 0
        self.state.clear_bases()
        self.context.half = half
        self.context.loop_state = MatchState.WAITING_FOR_PITCH
        self._state_change(
            "INNING_HALF",
            {"inning": self.state.inning, "half": half},
        )

    def _apply_outcome(self, outcome: PlayOutcome) -> Optional[GameResult]:
        half = self.state.top_bottom
        self._current_inning_runs[half] += outcome.runs_scored
        if not outcome.half_complete:
            return None
        action = self._end_half()
        if action == "start_bottom":
            return None
        skip_bottom = action == "record_skip"
        game_should_end = self._should_end_game_after_half(skip_bottom=skip_bottom)
        self._record_inning(skip_bottom=skip_bottom)
        if game_should_end:
            return self._finalize_game()
        return None

    def _end_half(self) -> str:
        if self.state.top_bottom == HALF_TOP:
            if self._should_skip_bottom():
                return "record_skip"
            self._begin_half(HALF_BOT)
            return "start_bottom"
        return "record_full"

    def _record_inning(self, *, skip_bottom: bool) -> None:
        inning_number = self.state.inning
        top_runs = self._current_inning_runs[HALF_TOP]
        bottom_runs = None if skip_bottom else self._current_inning_runs[HALF_BOT]
        self.scoreboard.record_inning(inning_number, top_runs, bottom_runs)
        self.scoreboard.print_board(self.state, io=self.io)
        flush_pitch_xp(self.state)
        self.state.inning += 1
        self.state.top_bottom = HALF_TOP
        self.context.inning = self.state.inning
        self.context.half = HALF_TOP
        self._needs_inning_setup = True

    def _should_skip_bottom(self) -> bool:
        return self.state.inning >= 9 and self.state.home_score > self.state.away_score

    def _home_walkoff_ready(self) -> bool:
        return self.state.inning >= 9 and self.state.home_score > self.state.away_score

    # --- Legacy compatibility helpers (used by existing tests) ---
    def _run_inning(self) -> None:
        inning_number = self.state.inning
        self._state_change("INNING_START", {"inning": inning_number})
        top_runs = self._execute_half_inning(HALF_TOP)
        if self._should_skip_bottom():
            self.scoreboard.record_inning(inning_number, top_runs, None)
            return
        bottom_runs = self._execute_half_inning(HALF_BOT)
        self.scoreboard.record_inning(inning_number, top_runs, bottom_runs)
        self._emit(EventType.SCOREBOARD_UPDATE.value, self._scoreboard_snapshot())

    def _execute_half_inning(self, half: str) -> int:
        state = self.state
        state.top_bottom = HALF_TOP if half == HALF_TOP else HALF_BOT
        state.outs = 0
        state.clear_bases()
        start_runs = state.away_score if half == HALF_TOP else state.home_score
        lineup_attr = "away_lineup" if half == HALF_TOP else "home_lineup"
        self._state_change("INNING_HALF", {"inning": state.inning, "half": state.top_bottom})
        while state.outs < 3:
            lineup = getattr(state, lineup_attr)
            batter = lineup[0] if lineup else None
            team_id = getattr(batter, "team_id", getattr(batter, "school_id", None))
            human_team_ids = getattr(state, "human_team_ids", set()) or set()
            user_controls = team_id in human_team_ids
            input_source = HumanBatterInput(io=self.io) if user_controls else CpuBatterInput()
            try:
                AtBatStateMachine(state, input_source=input_source).run()
            except TypeError:
                # Backward compatibility for tests that monkeypatch a simple callable
                AtBatStateMachine(state).run()
            setattr(state, lineup_attr, _rotate_lineup(getattr(state, lineup_attr)))
            if half == HALF_BOT and self._home_walkoff_ready():
                state.outs = 3
                break
        if half == HALF_TOP:
            return state.away_score - start_runs
        return state.home_score - start_runs

    def is_game_over(self) -> bool:
        skip_bottom = self._should_skip_bottom() if self.state.top_bottom == HALF_TOP else False
        return self._should_end_game_after_half(skip_bottom=skip_bottom)

    def _should_continue(self) -> bool:
        inning = self.state.inning
        home_score = self.state.home_score
        away_score = self.state.away_score
        if inning < 9:
            return True
        if home_score != away_score:
            return False
        if inning >= 12:
            self._state_change(
                "DRAW",
                {"inning": inning, "home_score": home_score, "away_score": away_score},
            )
            return False
        self._state_change(
            "EXTRA_INNINGS",
            {"inning": inning, "home_score": home_score, "away_score": away_score},
        )
        return True

    def _should_end_game_after_half(self, *, skip_bottom: bool) -> bool:
        inning = self.state.inning
        if inning < 9:
            return False
        if skip_bottom:
            return True
        if self.state.home_score != self.state.away_score:
            return True
        if inning >= 12:
            self._state_change(
                "DRAW",
                {
                    "inning": inning,
                    "home_score": self.state.home_score,
                    "away_score": self.state.away_score,
                },
            )
            return True
        self._state_change(
            "EXTRA_INNINGS",
            {
                "inning": inning,
                "home_score": self.state.home_score,
                "away_score": self.state.away_score,
            },
        )
        return False

    def _finalize_game(self) -> GameResult:
        if self._winner is None:
            if self.state.home_score > self.state.away_score:
                self._winner = self.state.home_team
            elif self.state.away_score > self.state.home_score:
                self._winner = self.state.away_team
        self._emit_game_over(self._winner)
        self._finished = True
        return GameResult(self._winner)

    def _state_change(self, phase: str, payload: Optional[Dict[str, Any]] = None) -> None:
        data = payload or {}
        data["phase"] = phase
        self._emit("MATCH_STATE_CHANGE", data)

    def _emit_game_over(self, winner) -> None:
        payload = {
            "home_score": self.state.home_score,
            "away_score": self.state.away_score,
            "home_team_name": getattr(self.state.home_team, "name", "Home"),
            "away_team_name": getattr(self.state.away_team, "name", "Away"),
            "winner_id": getattr(winner, "id", None) if winner else None,
            "winner_name": getattr(winner, "name", None) if winner else None,
        }
        self._emit("GAME_OVER", payload)

    def _emit(self, event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self.bus:
            self.bus.publish(event_name, payload or {})

def _finalize_rivalry_context(state, winner_team_id: Optional[int]) -> None:
    ctx = getattr(state, "rival_match_context", None)
    if not ctx:
        return
    ctx.finalize(winner_team_id)
    summary = ctx.rival.describe()
    hero_team_id = getattr(state, "hero_school_id", None)
    rival_team_id = getattr(ctx, "rival_team_id", None)
    hero_name = getattr(state, "hero_name", None) or "Hero"
    rival_name = getattr(state, "rival_name", None) or "Rival"
    result = "draw"
    if winner_team_id and hero_team_id:
        if winner_team_id == hero_team_id:
            result = "hero_win"
        elif rival_team_id and winner_team_id == rival_team_id:
            result = "rival_win"
        else:
            result = "other_win"
    summary.update(
        {
            "hero_name": hero_name,
            "rival_name": rival_name,
            "hero_team_id": hero_team_id,
            "rival_team_id": rival_team_id,
            "result": result,
        }
    )
    state.rival_postgame = summary
    log_line = (
        f"[Rivals] {hero_name} vs {rival_name}: {summary['record']['wins']}-"
        f"{summary['record']['losses']} heat {summary['heat_level']:.1f} ({result})."
    )
    logs = getattr(state, "logs", None)
    if isinstance(logs, list):
        logs.append(log_line)


@dataclass
class MatchContext:
    """Lightweight snapshot describing pacing metadata."""

    inning: int
    half: str
    loop_state: MatchState = MatchState.WAITING_FOR_PITCH
    awaiting_input: bool = False
    last_outcome: Optional[PlayOutcome] = None


@dataclass
class GameResult:
    """Return type emitted when the controller finishes a game."""

    winner: Any


class MatchController:
    """Owns the paced match loop and delegates at-bats to MatchSimulation."""

    def __init__(
        self,
        state,
        scoreboard: Scoreboard,
        *,
        human_team_ids: Optional[Sequence[int]] = None,
        io: Optional[IOInterface] = None,
    ) -> None:
        self.state = state
        self.scoreboard = scoreboard
        self.io = io
        event_bus = getattr(state, "event_bus", None)
        self.bus: EventBus = event_bus if isinstance(event_bus, EventBus) else EventBus()
        if not hasattr(state, "event_bus") or state.event_bus is None:
            state.event_bus = self.bus
        if io is not None:
            setattr(self.state, "io", io)
        self._install_fielding_trust_map(state)
        self.simulation = MatchSimulation(
            state,
            bus=self.bus,
            human_team_ids=human_team_ids,
        )
        self.context = MatchContext(inning=state.inning, half=state.top_bottom)
        self._started = False
        self._needs_inning_setup = True
        self._current_inning_runs = {HALF_TOP: 0, HALF_BOT: 0}
        self._finished = False
        self._winner = None
        self.telemetry = ensure_collector(state)
        self._walkoff_logged = False
        # Macro pacing controls
        self._hero_setting = getattr(state, "hero_setting", "key")  # "never", "key", "often"
        self._hero_cooldown_pa = getattr(state, "hero_cooldown_pa", 3)
        self._hero_cooldown_until = 0
        self._pa_counter = getattr(state, "pa_counter", 0)
        self._last_mode = None
        if not hasattr(self.state, "play_mode"):
            self.state.play_mode = PlayMode.SIM.value
        if not hasattr(self.state, "standing_orders"):
            self.state.standing_orders = {"offense": "Work the Count", "defense": "Attack Zone"}
        # Mirror user preference to listeners
        self._emit(EventType.HERO_MODE_SETTING.value, {"hero_setting": self._hero_setting})

    def _install_fielding_trust_map(self, state) -> None:
        """Precompute light fielding trust scalars from relationship seeds."""

        roster_map = getattr(state, "team_rosters", {}) or {}
        session = getattr(state, "db_session", None)
        if not session or not roster_map:
            state.fielding_trust_scalar = {}
            return
        trust: Dict[int, float] = {}
        for team_id, roster in roster_map.items():
            if not roster:
                continue
            totals = []
            for player in roster:
                try:
                    rel = seed_relationships(session, player)
                except Exception:
                    continue
                captain = getattr(rel, "captain_rel", 50) or 50
                battery = getattr(rel, "battery_rel", 50) or 50
                totals.append((captain + battery) / 2.0)
            if not totals:
                continue
            avg = sum(totals) / len(totals)
            # High trust trims errors slightly; low trust inflates them a touch.
            scalar = 1.0 - ((avg - 50.0) / 500.0)
            trust[team_id] = max(0.9, min(1.08, scalar))
        state.fielding_trust_scalar = trust

    def start_game(self):
        """Run the game to completion (legacy helper)."""

        while True:
            result = self.step()
            if isinstance(result, GameResult):
                return result.winner

    def step(self) -> GameResult | PlayOutcome | None:
        if self._finished:
            return GameResult(self._winner)

        if not self._started:
            self._start_match()
            return None

        if self._needs_inning_setup:
            self._prepare_inning()
            self._needs_inning_setup = False
            return None

        # Ensure simulation respects current macro play mode
        play_mode = getattr(self.state, "play_mode", PlayMode.SIM.value)
        if play_mode != self._last_mode:
            if play_mode == PlayMode.HERO.value and hasattr(self.simulation, "_pending_cut_in"):
                self.simulation._pending_cut_in = True
                logs = getattr(self.state, "logs", None)
                if isinstance(logs, list):
                    logs.append("[Cut-In] HERO mode engages — cameras zoom for the showdown.")
            self._emit(
                EventType.HERO_MODE_ENTER.value if play_mode == PlayMode.HERO.value else EventType.HERO_MODE_EXIT.value,
                {"mode": play_mode, "standing_orders": self.state.standing_orders},
            )
            self._emit(
                EventType.PLAY_MODE_CHANGED.value,
                {"mode": play_mode, "standing_orders": self.state.standing_orders},
            )
            self._last_mode = play_mode

        outcome = self.simulation.step()
        self.context.loop_state = self.simulation.loop_state
        self.context.awaiting_input = self.simulation.awaiting_player_choice
        if outcome is None:
            return None
        self.context.last_outcome = outcome
        result = self._apply_outcome(outcome)
        return result or outcome

    def _start_match(self) -> None:
        self._started = True
        self._state_change(
            "MATCH_START",
            {
                "home_team_id": getattr(self.state.home_team, "id", None),
                "away_team_id": getattr(self.state.away_team, "id", None),
                "home_team_name": getattr(self.state.home_team, "name", "Home"),
                "away_team_name": getattr(self.state.away_team, "name", "Away"),
            },
        )
        _emit_lineup_event(self.state)

    def _prepare_inning(self) -> None:
        manage_team_between_innings(self.state, "Home", io=self.io)
        manage_team_between_innings(self.state, "Away", io=self.io)
        self._state_change(
            "INNING_READY",
            {"inning": self.state.inning, "half": HALF_TOP},
        )
        self._current_inning_runs = {HALF_TOP: 0, HALF_BOT: 0}
        self._begin_half(HALF_TOP)

    def _begin_half(self, half: str) -> None:
        self.state.top_bottom = half
        self.state.outs = 0
        self.state.clear_bases()
        self.context.half = half
        self.context.loop_state = MatchState.WAITING_FOR_PITCH
        self._state_change(
            "INNING_HALF",
            {"inning": self.state.inning, "half": half},
        )

    def _apply_outcome(self, outcome: PlayOutcome) -> Optional[GameResult]:
        half = self.state.top_bottom
        play_detail = getattr(self.state, "latest_play_detail", None) or {}
        if outcome.error_on_play and hasattr(self.scoreboard, "record_error"):
            runs_on_play = play_detail.get("runs_scored", outcome.runs_scored)
            self.scoreboard.record_error(
                outcome.fielding_team,
                position=outcome.error_position,
                error_type=outcome.error_type,
                runs_scored=runs_on_play,
            )
        self._current_inning_runs[half] += outcome.runs_scored
        if (
            half == HALF_BOT
            and outcome.runs_scored > 0
            and self._home_walkoff_ready()
            and not self._walkoff_logged
        ):
            detail = play_detail.copy() if isinstance(play_detail, dict) else {}
            self.telemetry.record_walkoff(
                inning=self.state.inning,
                runs_scored=self._current_inning_runs[HALF_BOT],
                detail=detail,
            )
            self._walkoff_logged = True
        if not outcome.half_complete:
            return None
        action = self._end_half()
        if action == "start_bottom":
            return None
        skip_bottom = action == "record_skip"
        game_should_end = self._should_end_game_after_half(skip_bottom=skip_bottom)
        self._record_inning(skip_bottom=skip_bottom)
        if game_should_end:
            return self._finalize_game()
        return None

    # --- Macro pacing & drama ---
    def _maybe_update_play_mode(self, outcome: PlayOutcome) -> None:
        self._pa_counter += 1
        self.state.pa_counter = self._pa_counter
        setting = (getattr(self.state, "hero_setting", self._hero_setting) or "key").lower()
        if setting == "never":
            self.state.play_mode = PlayMode.SIM.value
            return

        # Cooldown to avoid rapid flipping
        if self._hero_cooldown_until and self._pa_counter < self._hero_cooldown_until:
            self.state.play_mode = PlayMode.SIM.value
            return

        drama_score = self._drama_score(outcome)
        threshold = 3 if setting == "key" else 2 if setting == "often" else 999

        if drama_score >= threshold:
            self.state.play_mode = PlayMode.HERO.value
            self._hero_cooldown_until = self._pa_counter + max(1, self._hero_cooldown_pa)
            self._emit(EventType.HERO_MODE_COOLDOWN.value, {"until_pa": self._hero_cooldown_until})
        else:
            self.state.play_mode = PlayMode.SIM.value

    def _drama_score(self, outcome: PlayOutcome) -> int:
        state = self.state
        score = 0
        inning = getattr(state, "inning", 1)
        half = getattr(state, "top_bottom", HALF_TOP)
        outs = getattr(state, "outs", 0)
        runners = getattr(state, "runners", [None, None, None])
        bases_loaded = all(runners)
        risp = any(runners[1:])
        run_diff = abs(getattr(state, "home_score", 0) - getattr(state, "away_score", 0))
        late = inning >= 8
        walkoff_window = half == HALF_BOT and inning >= 9 and getattr(state, "home_score", 0) <= getattr(state, "away_score", 0) + 1

        if bases_loaded and outs == 2:
            score += 4
        elif bases_loaded:
            score += 3
        if risp and outs >= 2:
            score += 2
        if late and run_diff <= 2:
            score += 2
        if walkoff_window:
            score += 3
        if getattr(state, "momentum_system", None):
            try:
                momentum_value = state.momentum_system.current_value()
                if abs(momentum_value) >= 3:
                    score += 1
            except Exception:
                pass
        return score

    def _end_half(self) -> str:
        if self.state.top_bottom == HALF_TOP:
            if self._should_skip_bottom():
                return "record_skip"
            self._begin_half(HALF_BOT)
            return "start_bottom"
        return "record_full"

    def _record_inning(self, *, skip_bottom: bool) -> None:
        inning_number = self.state.inning
        top_runs = self._current_inning_runs[HALF_TOP]
        bottom_runs = None if skip_bottom else self._current_inning_runs[HALF_BOT]
        self.scoreboard.record_inning(inning_number, top_runs, bottom_runs)
        self.scoreboard.print_board(self.state, io=self.io)
        summary = self.scoreboard.get_inning_summary(inning_number)
        if summary:
            self.telemetry.record_inning(
                inning=summary["inning"],
                top_runs=summary["away_runs"],
                bottom_runs=summary["home_runs"],
                skipped_bottom=skip_bottom,
            )
        flush_pitch_xp(self.state)
        self.state.inning += 1
        self.state.top_bottom = HALF_TOP
        self.context.inning = self.state.inning
        self.context.half = HALF_TOP
        self._needs_inning_setup = True

    def _should_skip_bottom(self) -> bool:
        return self.state.inning >= 9 and self.state.home_score > self.state.away_score

    def _home_walkoff_ready(self) -> bool:
        return self.state.inning >= 9 and self.state.home_score > self.state.away_score

    # --- Legacy compatibility helpers (used by existing tests) ---
    def _run_inning(self) -> None:
        inning_number = self.state.inning
        self._state_change("INNING_START", {"inning": inning_number})
        top_runs = self._execute_half_inning(HALF_TOP)
        if self._should_skip_bottom():
            self.scoreboard.record_inning(inning_number, top_runs, None)
            return
        bottom_runs = self._execute_half_inning(HALF_BOT)
        self.scoreboard.record_inning(inning_number, top_runs, bottom_runs)
        self._emit(EventType.SCOREBOARD_UPDATE.value, self._scoreboard_snapshot())

    def _execute_half_inning(self, half: str) -> int:
        state = self.state
        state.top_bottom = HALF_TOP if half == HALF_TOP else HALF_BOT
        state.outs = 0
        state.clear_bases()
        start_runs = state.away_score if half == HALF_TOP else state.home_score
        lineup_attr = "away_lineup" if half == HALF_TOP else "home_lineup"
        self._state_change("INNING_HALF", {"inning": state.inning, "half": state.top_bottom})
        while state.outs < 3:
            lineup = getattr(state, lineup_attr)
            batter = lineup[0] if lineup else None
            team_id = getattr(batter, "team_id", getattr(batter, "school_id", None))
            human_team_ids = getattr(state, "human_team_ids", set()) or set()
            user_controls = team_id in human_team_ids
            input_source = HumanBatterInput(io=self.io) if user_controls else CpuBatterInput()
            try:
                AtBatStateMachine(state, input_source=input_source).run()
            except TypeError:
                # Backward compatibility for legacy tests that monkeypatch a simple callable
                AtBatStateMachine(state).run()
            setattr(state, lineup_attr, _rotate_lineup(getattr(state, lineup_attr)))
            if half == HALF_BOT and self._home_walkoff_ready():
                state.outs = 3
                break
        if half == HALF_TOP:
            return state.away_score - start_runs
        return state.home_score - start_runs

    def is_game_over(self) -> bool:
        skip_bottom = self._should_skip_bottom() if self.state.top_bottom == HALF_TOP else False
        return self._should_end_game_after_half(skip_bottom=skip_bottom)

    def _should_continue(self) -> bool:
        inning = self.state.inning
        home_score = self.state.home_score
        away_score = self.state.away_score
        if inning < 9:
            return True
        if home_score != away_score:
            return False
        if inning >= 12:
            self._state_change(
                "DRAW",
                {"inning": inning, "home_score": home_score, "away_score": away_score},
            )
            return False
        self._state_change(
            "EXTRA_INNINGS",
            {"inning": inning, "home_score": home_score, "away_score": away_score},
        )
        return True

    def _should_end_game_after_half(self, *, skip_bottom: bool) -> bool:
        inning = self.state.inning
        if inning < 9:
            return False
        if skip_bottom:
            return True
        if self.state.home_score != self.state.away_score:
            return True
        if inning >= 12:
            self._state_change(
                "DRAW",
                {
                    "inning": inning,
                    "home_score": self.state.home_score,
                    "away_score": self.state.away_score,
                },
            )
            return True
        self._state_change(
            "EXTRA_INNINGS",
            {
                "inning": inning,
                "home_score": self.state.home_score,
                "away_score": self.state.away_score,
            },
        )
        return False

    def _finalize_game(self) -> GameResult:
        if self._winner is None:
            if self.state.home_score > self.state.away_score:
                self._winner = self.state.home_team
            elif self.state.away_score > self.state.home_score:
                self._winner = self.state.away_team
        self._flush_trust_buffer()
        _finalize_rivalry_context(self.state, getattr(self._winner, "id", None))
        error_summary = self.scoreboard.get_error_summary()
        setattr(self.state, "error_summary", error_summary)
        self._emit_game_over(self._winner, error_summary)
        self.telemetry.record_game_over(
            home_score=self.state.home_score,
            away_score=self.state.away_score,
            winner_id=getattr(self._winner, "id", None) if self._winner else None,
        )
        tilt_map = getattr(self.state, "umpire_call_tilt", {}) or {}
        self.telemetry.record_umpire_tilt(
            home_team_id=getattr(self.state.home_team, "id", None),
            away_team_id=getattr(self.state.away_team, "id", None),
            tilt_map=tilt_map,
        )
        flush_telemetry(self.state)
        self._finished = True
        return GameResult(self._winner)

    def _flush_trust_buffer(self) -> None:
        buffer = self.simulation.pop_trust_buffer()
        if buffer and not getattr(self.state, "fast_sim", False):
            apply_trust_buffer(buffer)

    def _state_change(self, phase: str, payload: Optional[Dict[str, Any]] = None) -> None:
        data = payload or {}
        data["phase"] = phase
        self._emit("MATCH_STATE_CHANGE", data)

    def _emit_game_over(self, winner, error_summary=None) -> None:
        payload = {
            "home_score": self.state.home_score,
            "away_score": self.state.away_score,
            "home_team_name": getattr(self.state.home_team, "name", "Home"),
            "away_team_name": getattr(self.state.away_team, "name", "Away"),
            "winner_id": getattr(winner, "id", None) if winner else None,
            "winner_name": getattr(winner, "name", None) if winner else None,
            "error_summary": error_summary or self.scoreboard.get_error_summary(),
        }
        self._emit("GAME_OVER", payload)

    def _scoreboard_snapshot(self) -> Dict[str, Any]:
        return {
            "innings": [list(inning) for inning in self.scoreboard.innings],
            "home_score": self.state.home_score,
            "away_score": self.state.away_score,
            "home_team_name": getattr(self.state.home_team, "name", "Home"),
            "away_team_name": getattr(self.state.away_team, "name", "Away"),
            "errors": self.scoreboard.get_error_summary(),
        }

    def _emit(self, event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self.bus:
            self.bus.publish(event_name, payload or {})

def run_match(
    home_id,
    away_id,
    *,
    fast: bool = False,
    silent: bool = False,
    auto_play_inputs: bool = False,
    persist_results: bool = True,
    clutch_pitch: Optional[Dict[str, Any]] = None,
    tournament_name: Optional[str] = None,
    human_team_ids: Optional[Sequence[int]] = None,
    hero_setting: str = "often",
    force_hero: bool = False,
    manual_pitch_calls: bool = False,
    manual_swing_prompts: bool = False,
    manual_fielding_prompts: bool = False,
    rival_match_context=None,
    rival_presentation: Optional[Dict[str, Any]] = None,
    session_provider: SessionProvider | None = None,
    temp_effects_store: TempEffects | None = None,
    session=None,
    io: Optional[IOInterface] = None,
):
    """Main entry point. Call this to play a full game."""

    external_session = session is not None
    provider = session_provider or SessionProvider(get_session, initial_session=session)
    owns_provider = session_provider is None and not external_session
    db_session = provider.get()
    previous_commentary = commentary_enabled()
    if fast or silent:
        set_commentary_enabled(False)

    try:
        prepare_kwargs: Dict[str, Any] = {
            "clutch_pitch": clutch_pitch,
            "tournament_name": tournament_name,
        }
        if rival_match_context is not None:
            prepare_kwargs["rival_match_context"] = rival_match_context

        state = prepare_match(
            home_id,
            away_id,
            db_session,
            **prepare_kwargs,
            session_provider=provider,
            temp_effects_store=temp_effects_store,
        )
        if not state:
            return None
        # Attach scoped temp effects store if not present
        if not getattr(state, "temp_effects_store", None):
            setattr(state, "temp_effects_store", temp_effects_store or TempEffects())
        if rival_presentation:
            state.rival_presentation = rival_presentation

        if fast:
            setattr(state, "fast_sim", True)
        if auto_play_inputs or fast:
            setattr(state, "auto_play_inputs", True)
            setattr(state, "manual_pitch_calls", False)
            setattr(state, "manual_swing_prompts", False)
            state.human_team_ids = set()

        # Enable user-controlled pacing if requested
        state.hero_setting = hero_setting
        if force_hero:
            state.play_mode = PlayMode.HERO.value
        if manual_pitch_calls:
            state.manual_pitch_calls = True
        if manual_swing_prompts:
            state.manual_swing_prompts = True
        if manual_fielding_prompts:
            state.manual_fielding_prompts = True

        if not fast:
            bus = getattr(state, "event_bus", None)
            if bus:
                bus.publish("MATCH_INTRO", {"home_team_id": home_id, "away_team_id": away_id})

        CommentaryListener(getattr(state, "event_bus", None), io=io)
        if not hasattr(state, "telemetry_store_in_db"):
            state.telemetry_store_in_db = True

        scoreboard = Scoreboard()
        controller = MatchController(
            state,
            scoreboard,
            human_team_ids=human_team_ids,
            io=io,
        )

        winner = controller.start_game()
        bus = getattr(state, "event_bus", None)
        summary_line = summarize_mastery_report(state)
        if bus:
            bus.publish(EventType.SCOREBOARD_UPDATE.value, controller._scoreboard_snapshot())
            if summary_line:
                bus.publish(EventType.PITCH_MASTERY_SUMMARY.value, {"summary": summary_line})

        if winner and persist_results:
            MatchPersistenceService.save_game_results(state)
            # Make sure downstream callers can inspect winner attributes after
            # this function closes the session.
            try:
                db_session.refresh(winner)
                db_session.expunge(winner)
            except Exception:
                pass
        return winner
    finally:
        set_commentary_enabled(previous_commentary)
        if owns_provider:
            provider.close()


_RESOLVE_MODE_PRESETS: Dict[str, Dict[str, bool]] = {
    "standard": {"fast": False, "silent": False},
    "interactive": {"fast": False, "silent": False},
    "fast": {"fast": True, "silent": False},
    "silent": {"fast": False, "silent": True},
}


def _fetch_latest_score(home_id: int, away_id: int, tournament_name: str, *, session=None) -> str:
    """Read the latest game for the two teams and optionally tag the tournament."""
    score_str = "0 - 0"
    managed_session = False
    db_session = session
    if db_session is None:
        managed_session = True
        ctx = session_scope()
        db_session = ctx.__enter__()

    try:
        game = (
            db_session.query(Game)
            .filter(
                Game.home_school_id == home_id,
                Game.away_school_id == away_id,
            )
            .order_by(Game.id.desc())
            .first()
        )
        if not game:
            return score_str

        score_str = f"{game.away_score} - {game.home_score}"
        if tournament_name != "Practice Match" and game.tournament != tournament_name:
            game.tournament = tournament_name
            db_session.commit()
    except Exception as exc:
        logger.exception("Failed to fetch latest score from database")
        raise RuntimeError("Failed to fetch latest score from database") from exc
    finally:
        if managed_session:
            ctx.__exit__(*sys.exc_info())

    return score_str


def _simulate_match(
    home_team,
    away_team,
    tournament_name: str,
    *,
    silent: bool,
    fast: bool,
    clutch_pitch: Optional[Dict[str, Any]] = None,
    rival_match_context=None,
    rival_presentation=None,
    persist_results: bool = True,
    session=None,
):
    auto_play_inputs = fast or silent
    human_team_ids = [] if auto_play_inputs else None

    managed_session = False
    db_session = session
    if db_session is None:
        managed_session = True
        ctx = session_scope()
        db_session = ctx.__enter__()

    try:
        if fast:
            winner = run_match(
                home_team.id,
                away_team.id,
                fast=True,
                silent=silent,
                auto_play_inputs=auto_play_inputs,
                persist_results=persist_results,
                clutch_pitch=clutch_pitch,
                tournament_name=tournament_name,
                human_team_ids=human_team_ids,
                rival_match_context=rival_match_context,
                rival_presentation=rival_presentation,
                session=db_session,
            )
        elif silent:
            winner = run_match(
                home_team.id,
                away_team.id,
                silent=True,
                auto_play_inputs=auto_play_inputs,
                clutch_pitch=clutch_pitch,
                tournament_name=tournament_name,
                persist_results=persist_results,
                human_team_ids=human_team_ids,
                rival_match_context=rival_match_context,
                rival_presentation=rival_presentation,
                session=db_session,
            )
        else:
            winner = run_match(
                home_team.id,
                away_team.id,
                auto_play_inputs=auto_play_inputs,
                clutch_pitch=clutch_pitch,
                tournament_name=tournament_name,
                persist_results=persist_results,
                human_team_ids=human_team_ids,
                rival_match_context=rival_match_context,
                rival_presentation=rival_presentation,
                session=db_session,
            )

        score_str = _fetch_latest_score(home_team.id, away_team.id, tournament_name, session=db_session)
        consume_strategy_mods(db_session, home_team.id)
        consume_strategy_mods(db_session, away_team.id)
        return winner, score_str
    finally:
        if managed_session:
            ctx.__exit__(*sys.exc_info())


def resolve_match(
    home_team,
    away_team,
    tournament_name: str = "Practice Match",
    *,
    mode: str = "standard",
    silent: Optional[bool] = None,
    clutch_pitch: Optional[Dict[str, Any]] = None,
    rival_match_context=None,
    rival_presentation=None,
    persist_results: bool = True,
):
    """Unified entry point for orchestrating a simulated match.

    The controller orchestrates; simulation remains pure and database writes stay here.
    """

    preset = _RESOLVE_MODE_PRESETS.get(mode)
    if preset is None:
        raise ValueError(f"Unknown resolve mode '{mode}'.")
    fast = preset["fast"]
    effective_silent = preset["silent"] if silent is None else silent
    winner = _simulate_match(
        home_team,
        away_team,
        tournament_name,
        silent=effective_silent,
        fast=fast,
        clutch_pitch=clutch_pitch,
        rival_match_context=rival_match_context,
        rival_presentation=rival_presentation,
        persist_results=persist_results,
    )
    return winner