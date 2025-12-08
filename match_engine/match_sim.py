"""Lightweight match simulation stub used by the controller and tests.

This implementation focuses on deterministic, non-interactive progression to
avoid the circular and corrupted state of the previous version. It advances
outs, emits rivalry cut-ins, and produces simple `PlayOutcome` records so
`MatchController` can drive games to completion (especially in fast/silent
modes used by tests).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Sequence

from core.event_bus import EventBus
from match_engine.states import EventType, HitType, InningHalf, MatchState, PlayMode
from match_engine.input_system import BatterInputSource, FixedBatterInput, HumanBatterInput, CpuBatterInput
from match_engine.batter_logic import AtBatStateMachine
from match_engine.interfaces import BatterLike, PitcherLike
from game.save_manager import autosave_match_state


logger = logging.getLogger(__name__)


@dataclass
class BatterChoice:
    key: str
    label: str
    action: str
    mods: Dict[str, int]
    guess_payload: Optional[Dict[str, Any]] = None
    description: str = ""


@dataclass
class MatchupContext:
    inning: int
    half: InningHalf
    pitcher: "PitcherLike"
    batter: "BatterLike"
    lineup_attr: str
    balls: int
    strikes: int
    outs_before: int
    home_score: int
    away_score: int
    batter_stats: Dict[str, Any]
    pitcher_stats: Dict[str, Any]
    is_human: bool


@dataclass
class PlayOutcome:
    inning: int
    half: InningHalf
    batter_id: Optional[int]
    pitcher_id: Optional[int]
    outs_recorded: int
    runs_scored: int
    description: str
    result_type: str
    half_complete: bool
    drama_level: int = 0
    batting_team: Optional[str] = None
    fielding_team: Optional[str] = None
    hit_type: Optional[HitType] = None
    double_play: bool = False
    error_on_play: bool = False
    error_type: Optional[str] = None
    error_position: Optional[str] = None


class InputStrategy(Protocol):
    """Strategy for selecting batter input without mutating global UI state."""

    def select_batter_choice(self, matchup: MatchupContext, choices: Dict[str, BatterChoice]) -> Optional[str]:
        ...


class MatchSimulation:
    """Simplified simulation loop that progresses outs and emits basic events."""

    def __init__(
        self,
        state,
        *,
        bus: Optional[EventBus] = None,
        human_team_ids: Optional[Sequence[int]] = None,
        input_strategy: Optional["InputStrategy"] = None,
    ) -> None:
        self.state = state
        self.bus: EventBus = bus if isinstance(bus, EventBus) else EventBus()
        self.human_team_ids = set(human_team_ids or [])
        self.input_strategy = input_strategy
        self.loop_state = MatchState.WAITING_FOR_PITCH
        self.awaiting_player_choice = False
        self._pending_choice_options: list[Dict[str, str]] = []
        self._pending_choice: Optional[BatterChoice] = None
        self._pending_cut_in = False
        self._current_matchup: Optional[MatchupContext] = None
        self._trust_buffer: Dict[tuple[int, int], float] = {}

    def step(self) -> Optional[PlayOutcome]:
        """Advance the simulation by one plate appearance or pause for cut-ins."""
        self.loop_state = MatchState.WAITING_FOR_PITCH
        if self._pending_cut_in:
            self._pending_cut_in = False
            return None

        # Phase 1: Build the matchup and surface any cut-ins or player choices.
        if self._current_matchup is None:
            matchup = self._build_matchup()
            if matchup is None:
                return None
            self._current_matchup = matchup

            if self._is_rivalry_moment(matchup) and self._emit_rival_cut_in(matchup):
                self._pending_cut_in = True
                return None

            if self.input_strategy:
                try:
                    choice_key = self.input_strategy.select_batter_choice(matchup, self._CHOICE_LIBRARY)
                    if choice_key:
                        self.submit_player_choice(choice_key)
                except Exception as exc:
                    # Surface strategy failures so they do not fail silently and mask defects.
                    logger.exception("Input strategy failed during batter choice selection")
                    raise RuntimeError("Input strategy failed during batter choice selection") from exc

            self._active_input_source = self._select_input_source(matchup)
            return None

        # Phase 2: Execute the matchup built on the previous call.
        try:
            # If an earlier error cleared the input source, fall back to CPU to avoid deadlock.
            if self._active_input_source is None:
                self._active_input_source = self._select_input_source(self._current_matchup)

            outcome = self._execute_matchup()
            outcome = self._summarize_outcome(outcome)
            if getattr(outcome, "drama_level", 0) >= 4:
                try:
                    autosave_match_state(state=self.state, reason="high_drama_play")
                except Exception:
                    pass
            return outcome
        finally:
            # Always reset internal phase markers to avoid zombie matchups on errors.
            self.loop_state = MatchState.WAITING_FOR_PITCH
            self._current_matchup = None
            self._pending_cut_in = False
            self._pending_choice = None
            self.awaiting_player_choice = False

    def submit_player_choice(self, choice_key: str) -> None:
        if choice_key not in self._CHOICE_LIBRARY:
            raise ValueError(f"Unknown Batter's Eye choice '{choice_key}'.")
        self._pending_choice = self._CHOICE_LIBRARY[choice_key]
        self.awaiting_player_choice = False

    def pending_choice_options(self) -> Sequence[Dict[str, str]]:
        return tuple(self._pending_choice_options)

    def pop_trust_buffer(self) -> Dict[tuple[int, int], float]:
        buffer = self._trust_buffer
        self._trust_buffer = {}
        return buffer

    def _normalize_half(self, half: Optional[Any]) -> InningHalf:
        if half is None:
            raise ValueError("MatchSimulation requires state.top_bottom to be set before stepping.")
        if isinstance(half, InningHalf):
            return half

        candidate = getattr(half, "value", half)
        if isinstance(candidate, str):
            label = candidate.strip().lower()
            if label in {"top", "t"}:
                return InningHalf.TOP
            if label in {"bot", "bottom", "b"}:
                return InningHalf.BOT

        raise ValueError(f"Invalid inning half '{half}'. Expected Top/Bot or InningHalf enum.")

    def _validate_state(self) -> InningHalf:
        half = self._normalize_half(getattr(self.state, "top_bottom", None))
        lineup_attr = "away_lineup" if half == InningHalf.TOP else "home_lineup"
        lineup = getattr(self.state, lineup_attr, None)
        if not lineup:
            raise ValueError(f"Lineup '{lineup_attr}' must be populated before stepping the match sim.")
        pitcher = self.state.home_pitcher if half == InningHalf.TOP else self.state.away_pitcher
        if pitcher is None:
            raise ValueError(f"Pitcher must be assigned for the {half.value} of inning {getattr(self.state, 'inning', '?')}.")
        self.state.top_bottom = half
        return half

    def _build_matchup(self) -> Optional[MatchupContext]:
        half = self._validate_state()
        lineup_attr = "away_lineup" if half == InningHalf.TOP else "home_lineup"
        lineup = getattr(self.state, lineup_attr, None) or []
        if not lineup:
            return None
        batter = lineup[0]
        pitcher = self.state.home_pitcher if half == InningHalf.TOP else self.state.away_pitcher
        batter_id = getattr(batter, "id", None)
        pitcher_id = getattr(pitcher, "id", None)
        return MatchupContext(
            inning=self.state.inning,
            half=half,
            pitcher=pitcher,
            batter=batter,
            lineup_attr=lineup_attr,
            balls=getattr(self.state, "balls", 0),
            strikes=getattr(self.state, "strikes", 0),
            outs_before=getattr(self.state, "outs", 0),
            home_score=getattr(self.state, "home_score", 0),
            away_score=getattr(self.state, "away_score", 0),
            batter_stats=self.state.get_stats(batter_id) if callable(getattr(self.state, "get_stats", None)) else {},
            pitcher_stats=self.state.get_stats(pitcher_id) if callable(getattr(self.state, "get_stats", None)) else {},
            is_human=self._is_user_controlled(batter),
        )

    def _select_input_source(self, matchup: MatchupContext) -> Optional[BatterInputSource]:
        # Forced choice takes priority
        if self._pending_choice:
            return FixedBatterInput(self._pending_choice)

        # Human-controlled batter gets human input strategy if available
        if matchup.is_human:
            return HumanBatterInput(io=getattr(self.state, "io", None))

        # CPU fallback
        return CpuBatterInput()

    def _execute_matchup(self) -> PlayOutcome:
        assert self._current_matchup is not None
        self.loop_state = MatchState.PITCH_FLIGHT

        # Allow patched/mock state machines to observe PITCH_FLIGHT state.
        try:
            AtBatStateMachine(self.state, input_source=self._active_input_source).run()
        except Exception as exc:
            logger.exception("AtBatStateMachine crashed during matchup execution")
            raise RuntimeError("AtBatStateMachine crashed during matchup execution") from exc

        self.loop_state = MatchState.PLAY_RESOLUTION

        batter_id = getattr(self._current_matchup.batter, "id", None)
        pitcher_id = getattr(self._current_matchup.pitcher, "id", None)
        batting_side = self._batting_side(self._current_matchup.half)
        fielding_side = self._fielding_side(self._current_matchup.half)

        outs_before = self._current_matchup.outs_before
        home_before = self._current_matchup.home_score
        away_before = self._current_matchup.away_score

        payload = {
            "inning": self._current_matchup.inning,
            "half": self._current_matchup.half,
            "batter_id": batter_id,
            "pitcher_id": pitcher_id,
        }
        self.bus.publish(EventType.PITCH_THROWN.value, payload)

        outs_after = getattr(self.state, "outs", outs_before)
        outs_recorded = max(0, outs_after - outs_before)
        home_after = getattr(self.state, "home_score", home_before)
        away_after = getattr(self.state, "away_score", away_before)

        runs_scored = (away_after - away_before) if batting_side == "away" else (home_after - home_before)

        half_complete = outs_after >= 3 or self._home_walkoff_ready()
        result_type = "run_scored" if runs_scored > 0 else ("out_recorded" if outs_recorded > 0 else "in_play")

        outcome = PlayOutcome(
            inning=self.state.inning,
            half=self.state.top_bottom,
            batter_id=batter_id,
            pitcher_id=pitcher_id,
            outs_recorded=outs_recorded,
            runs_scored=runs_scored,
            description="Plate appearance resolved",
            result_type=result_type,
            half_complete=half_complete,
            drama_level=0,
            batting_team=batting_side,
            fielding_team=fielding_side,
        )

        self.bus.publish(
            EventType.PLAY_RESULT.value,
            {
                "inning": outcome.inning,
                "half": outcome.half,
                "batter_id": outcome.batter_id,
                "pitcher_id": outcome.pitcher_id,
                "result_type": outcome.result_type,
                "outs_recorded": outcome.outs_recorded,
                "runs_scored": outcome.runs_scored,
                "description": outcome.description,
                "batting_team": batting_side,
                "fielding_team": fielding_side,
            },
        )

        return outcome

    def _summarize_outcome(self, outcome: PlayOutcome) -> PlayOutcome:
        return outcome

    def _is_user_controlled(self, player: Any) -> bool:
        team_id = getattr(player, "team_id", getattr(player, "school_id", None))
        if getattr(player, "is_user_controlled", False):
            return True
        if team_id is None:
            return False
        return team_id in self.human_team_ids

    def _batting_side(self, half: Optional[str] = None) -> str:
        normalized_half = self._normalize_half(half or getattr(self.state, "top_bottom", None))
        return "away" if normalized_half == InningHalf.TOP else "home"

    def _fielding_side(self, half: Optional[str] = None) -> str:
        return "home" if self._batting_side(half) == "away" else "away"

    def _home_walkoff_ready(self) -> bool:
        half = self._normalize_half(getattr(self.state, "top_bottom", None))
        return half == InningHalf.BOT and self.state.inning >= 9 and getattr(self.state, "home_score", 0) > getattr(self.state, "away_score", 0)

    def _is_rivalry_moment(self, matchup: MatchupContext) -> bool:
        ctx = getattr(self.state, "rival_match_context", None)
        if not ctx:
            return False
        batter_id = getattr(matchup.batter, "id", None)
        pitcher_id = getattr(matchup.pitcher, "id", None)
        return ctx.is_rival_plate(batter_id) or ctx.is_hero_pitching(pitcher_id)

    def _emit_rival_cut_in(self, matchup: MatchupContext) -> bool:
        memo = getattr(self.state, "commentary_memory", None)
        cache_key = f"rival_cutin_{matchup.inning}_{matchup.half}_{getattr(matchup.batter, 'id', None)}"
        if isinstance(memo, set) and cache_key in memo:
            return False
        hero = getattr(self.state, "hero_name", None) or "Hero"
        rival = getattr(self.state, "rival_name", None) or getattr(matchup.batter, "last_name", "Rival")
        payload = {
            "inning": matchup.inning,
            "half": matchup.half,
            "batter_id": getattr(matchup.batter, "id", None),
            "pitcher_id": getattr(matchup.pitcher, "id", None),
            "hero_name": hero,
            "rival_name": rival,
        }
        self.bus.publish(EventType.RIVAL_CUT_IN.value, payload)
        logs = getattr(self.state, "logs", None)
        if isinstance(logs, list):
            logs.append(f"[Rivalry] {hero} locks eyes with {rival} as the cut-in hits.")
        if isinstance(memo, set):
            memo.add(cache_key)
        return True


# Minimal Batter's Eye library for compatibility with old callers
MatchSimulation._CHOICE_LIBRARY = {
    "standard": BatterChoice(
        key="standard",
        label="Standard Swing",
        action="swing",
        mods={},
        description="Default swing with no guesses.",
    )
}


__all__ = ["MatchSimulation", "MatchupContext", "PlayOutcome", "InputStrategy", "resolve_match"]


def resolve_match(*args, **kwargs):
    """Compatibility shim forwarding to the controller's resolve_match."""

    from match_engine.controller import resolve_match as _resolve_match

    return _resolve_match(*args, **kwargs)
