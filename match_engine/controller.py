"""High-level orchestration for the match engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

import json


from core.event_bus import EventBus

from .pregame import prepare_match
from .match_sim import MatchSimulation, MatchupContext, PlayOutcome
from .commentary import CommentaryListener, commentary_enabled, set_commentary_enabled
from .scoreboard import Scoreboard
from .manager_ai import manage_team_between_innings
from .confidence import get_confidence_summary

from .telemetry import ensure_collector, flush_telemetry
from database.setup_db import get_session, Game, GameState, Performance, ensure_game_schema

from database.setup_db import get_session, Game, Performance, ensure_game_schema

from game.personality_effects import evaluate_postgame_slumps
from game.relationship_manager import apply_confidence_relationships
from .states import MatchState
from .batter_logic import AtBatStateMachine

from ui.ui_display import render_box_score_panel


def save_game_results(state):
    """
    Basic implementation of saving game results to DB.
    """
    # print("\nSaving Game Results...")
    ensure_game_schema()
    weather = getattr(state, 'weather', None)
    umpire = getattr(state, 'umpire', None)
    tilt = getattr(state, 'umpire_call_tilt', {}) or {}
    home_id = getattr(state.home_team, 'id', None)
    away_id = getattr(state.away_team, 'id', None)
    home_tilt = tilt.get(home_id, {"favored": 0, "squeezed": 0})
    away_tilt = tilt.get(away_id, {"favored": 0, "squeezed": 0})
    error_summary = getattr(state, "error_summary", None)
    g = Game(
        season_year=1, # Should pull from global state ideally
        tournament="Season Match",
        home_school_id=state.home_team.id, # FIXED: home_school_id
        away_school_id=state.away_team.id, # FIXED: away_school_id
        home_score=state.home_score, 
        away_score=state.away_score, 
        is_completed=True,
        weather_label=getattr(weather, 'label', None),
        weather_condition=getattr(weather, 'condition', None),
        weather_precip=getattr(weather, 'precipitation', None),
        weather_temperature_f=getattr(weather, 'temperature_f', None),
        weather_wind_speed=getattr(weather, 'wind_speed_mph', None),
        weather_wind_direction=getattr(weather, 'wind_direction', None),
        weather_summary=weather.describe() if weather else None,
        umpire_name=getattr(umpire, 'name', None),
        umpire_description=getattr(umpire, 'description', None),
        umpire_zone_bias=getattr(umpire, 'zone_bias', None),
        umpire_home_bias=getattr(umpire, 'home_bias', None),
        umpire_temperament=getattr(umpire, 'temperament', None),
        umpire_favored_home=home_tilt.get('favored', 0),
        umpire_squeezed_home=home_tilt.get('squeezed', 0),
        umpire_favored_away=away_tilt.get('favored', 0),
        umpire_squeezed_away=away_tilt.get('squeezed', 0),
        error_summary=json.dumps(error_summary) if error_summary is not None else None,
        rivalry_summary=json.dumps(getattr(state, 'rival_postgame', None)) if getattr(state, 'rival_postgame', None) else None,
    )
    db_session = state.db_session
    if db_session is None:
        raise ValueError("MatchState missing db_session for persistence.")

    db_session.add(g)
    db_session.flush()

    gamestate_row = db_session.query(GameState).first()
    if gamestate_row is not None:
        gamestate_row.last_error_summary = json.dumps(error_summary) if error_summary is not None else None
        db_session.add(gamestate_row)
    
    # Save Player Stats
    for p_id, s in state.stats.items():
        team_id = state.player_team_map.get(p_id)
        if team_id is None:
            is_home = any(p.id == p_id for p in state.home_roster if p) or getattr(state.home_pitcher, 'id', None) == p_id
            team_id = state.home_team.id if is_home else state.away_team.id
        
        perf = Performance(
            game_id=g.id,
            player_id=p_id,
            team_id=team_id, # This is fine if Performance table kept team_id column as generic ID
            at_bats=s["at_bats"],
            hits=s["hits"],
            homeruns=s["homeruns"],
            rbi=s["rbi"],
            strikeouts=s["strikeouts"],
            walks=s["walks"],
            innings_pitched=s["innings_pitched"],
            strikeouts_pitched=s["strikeouts_pitched"],
            runs_allowed=s["runs_allowed"],
            confidence=state.confidence_map.get(p_id, 0)
        )
        db_session.add(perf)
        
    state.confidence_summary_snapshot = get_confidence_summary(state)
    apply_confidence_relationships(db_session, state.confidence_summary_snapshot)
    evaluate_postgame_slumps(state)
    db_session.commit()
    # print("Game Saved!")


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
        agency_adapter: Optional[Callable[[MatchupContext], str]] = None,
    ) -> None:
        self.state = state
        self.scoreboard = scoreboard
        event_bus = getattr(state, "event_bus", None)
        self.bus: EventBus = event_bus if isinstance(event_bus, EventBus) else EventBus()
        if not hasattr(state, "event_bus") or state.event_bus is None:
            state.event_bus = self.bus
        self.simulation = MatchSimulation(
            state,
            bus=self.bus,
            human_team_ids=human_team_ids,
            agency_adapter=agency_adapter,
        )
        self.context = MatchContext(inning=state.inning, half=state.top_bottom)
        self._started = False
        self._needs_inning_setup = True
        self._current_inning_runs = {"Top": 0, "Bot": 0}
        self._finished = False
        self._winner = None

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
        manage_team_between_innings(self.state, "Home")
        manage_team_between_innings(self.state, "Away")
        self._state_change(
            "INNING_READY",
            {"inning": self.state.inning, "half": "Top"},
        )
        self._current_inning_runs = {"Top": 0, "Bot": 0}
        self._begin_half("Top")

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
        if self.state.top_bottom == "Top":
            if self._should_skip_bottom():
                return "record_skip"
            self._begin_half("Bot")
            return "start_bottom"
        return "record_full"

    def _record_inning(self, *, skip_bottom: bool) -> None:
        inning_number = self.state.inning
        top_runs = self._current_inning_runs["Top"]
        bottom_runs = None if skip_bottom else self._current_inning_runs["Bot"]
        self.scoreboard.record_inning(inning_number, top_runs, bottom_runs)
        self.scoreboard.print_board(self.state)
        self.state.inning += 1
        self.state.top_bottom = "Top"
        self.context.inning = self.state.inning
        self.context.half = "Top"
        self._needs_inning_setup = True

    def _should_skip_bottom(self) -> bool:
        return self.state.inning >= 9 and self.state.home_score > self.state.away_score

    def _home_walkoff_ready(self) -> bool:
        return self.state.inning >= 9 and self.state.home_score > self.state.away_score

    # --- Legacy compatibility helpers (used by existing tests) ---
    def _run_inning(self) -> None:
        inning_number = self.state.inning
        self._state_change("INNING_START", {"inning": inning_number})
        top_runs = self._execute_half_inning("Top")
        if self._should_skip_bottom():
            self.scoreboard.record_inning(inning_number, top_runs, None)
            return
        bottom_runs = self._execute_half_inning("Bot")
        self.scoreboard.record_inning(inning_number, top_runs, bottom_runs)
        self.scoreboard.print_board(self.state)

    def _execute_half_inning(self, half: str) -> int:
        state = self.state
        state.top_bottom = "Top" if half == "Top" else "Bot"
        state.outs = 0
        state.clear_bases()
        start_runs = state.away_score if half == "Top" else state.home_score
        lineup_attr = "away_lineup" if half == "Top" else "home_lineup"
        self._state_change("INNING_HALF", {"inning": state.inning, "half": state.top_bottom})
        while state.outs < 3:
            AtBatStateMachine(state).run()
            setattr(state, lineup_attr, _rotate_lineup(getattr(state, lineup_attr)))
            if half == "Bot" and self._home_walkoff_ready():
                state.outs = 3
                break
        if half == "Top":
            return state.away_score - start_runs
        return state.home_score - start_runs

    def is_game_over(self) -> bool:
        skip_bottom = self._should_skip_bottom() if self.state.top_bottom == "Top" else False
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
        agency_adapter: Optional[Callable[[MatchupContext], str]] = None,
    ) -> None:
        self.state = state
        self.scoreboard = scoreboard
        event_bus = getattr(state, "event_bus", None)
        self.bus: EventBus = event_bus if isinstance(event_bus, EventBus) else EventBus()
        if not hasattr(state, "event_bus") or state.event_bus is None:
            state.event_bus = self.bus
        self.simulation = MatchSimulation(
            state,
            bus=self.bus,
            human_team_ids=human_team_ids,
            agency_adapter=agency_adapter,
        )
        self.context = MatchContext(inning=state.inning, half=state.top_bottom)
        self._started = False
        self._needs_inning_setup = True
        self._current_inning_runs = {"Top": 0, "Bot": 0}
        self._finished = False
        self._winner = None
        self.telemetry = ensure_collector(state)
        self._walkoff_logged = False

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
        manage_team_between_innings(self.state, "Home")
        manage_team_between_innings(self.state, "Away")
        self._state_change(
            "INNING_READY",
            {"inning": self.state.inning, "half": "Top"},
        )
        self._current_inning_runs = {"Top": 0, "Bot": 0}
        self._begin_half("Top")

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
            half == "Bot"
            and outcome.runs_scored > 0
            and self._home_walkoff_ready()
            and not self._walkoff_logged
        ):
            detail = play_detail.copy() if isinstance(play_detail, dict) else {}
            self.telemetry.record_walkoff(
                inning=self.state.inning,
                runs_scored=self._current_inning_runs["Bot"],
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

    def _end_half(self) -> str:
        if self.state.top_bottom == "Top":
            if self._should_skip_bottom():
                return "record_skip"
            self._begin_half("Bot")
            return "start_bottom"
        return "record_full"

    def _record_inning(self, *, skip_bottom: bool) -> None:
        inning_number = self.state.inning
        top_runs = self._current_inning_runs["Top"]
        bottom_runs = None if skip_bottom else self._current_inning_runs["Bot"]
        self.scoreboard.record_inning(inning_number, top_runs, bottom_runs)
        self.scoreboard.print_board(self.state)
        summary = self.scoreboard.get_inning_summary(inning_number)
        if summary:
            self.telemetry.record_inning(
                inning=summary["inning"],
                top_runs=summary["away_runs"],
                bottom_runs=summary["home_runs"],
                skipped_bottom=skip_bottom,
            )
        self.state.inning += 1
        self.state.top_bottom = "Top"
        self.context.inning = self.state.inning
        self.context.half = "Top"
        self._needs_inning_setup = True

    def _should_skip_bottom(self) -> bool:
        return self.state.inning >= 9 and self.state.home_score > self.state.away_score

    def _home_walkoff_ready(self) -> bool:
        return self.state.inning >= 9 and self.state.home_score > self.state.away_score

    # --- Legacy compatibility helpers (used by existing tests) ---
    def _run_inning(self) -> None:
        inning_number = self.state.inning
        self._state_change("INNING_START", {"inning": inning_number})
        top_runs = self._execute_half_inning("Top")
        if self._should_skip_bottom():
            self.scoreboard.record_inning(inning_number, top_runs, None)
            return
        bottom_runs = self._execute_half_inning("Bot")
        self.scoreboard.record_inning(inning_number, top_runs, bottom_runs)
        self.scoreboard.print_board(self.state)

    def _execute_half_inning(self, half: str) -> int:
        state = self.state
        state.top_bottom = "Top" if half == "Top" else "Bot"
        state.outs = 0
        state.clear_bases()
        start_runs = state.away_score if half == "Top" else state.home_score
        lineup_attr = "away_lineup" if half == "Top" else "home_lineup"
        self._state_change("INNING_HALF", {"inning": state.inning, "half": state.top_bottom})
        while state.outs < 3:
            AtBatStateMachine(state).run()
            setattr(state, lineup_attr, _rotate_lineup(getattr(state, lineup_attr)))
            if half == "Bot" and self._home_walkoff_ready():
                state.outs = 3
                break
        if half == "Top":
            return state.away_score - start_runs
        return state.home_score - start_runs

    def is_game_over(self) -> bool:
        skip_bottom = self._should_skip_bottom() if self.state.top_bottom == "Top" else False
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

    def _emit(self, event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self.bus:
            self.bus.publish(event_name, payload or {})

def run_match(
    home_id,
    away_id,
    *,
    fast: bool = False,
    clutch_pitch: Optional[Dict[str, Any]] = None,
):
    """
    Main entry point. Call this to play a full game.
    """
    # 1. Setup
    db_session = get_session()
    previous_commentary = commentary_enabled()
    if fast:
        set_commentary_enabled(False)
    try:
        state = prepare_match(home_id, away_id, db_session, clutch_pitch=clutch_pitch)
        if not state:
            return None # Error handling
        CommentaryListener(getattr(state, "event_bus", None))
        if not hasattr(state, "telemetry_store_in_db"):
            state.telemetry_store_in_db = True
        scoreboard = Scoreboard()
        controller = MatchController(state, scoreboard)
        winner = controller.start_game()
        if not fast:
            render_box_score_panel(scoreboard, state)
        if winner:
            save_game_results(state)
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
        db_session.close()