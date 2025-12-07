"""Lightweight match simulation stub used by the controller and tests.

This implementation focuses on deterministic, non-interactive progression to
avoid the circular and corrupted state of the previous version. It advances
outs, emits rivalry cut-ins, and produces simple `PlayOutcome` records so
`MatchController` can drive games to completion (especially in fast/silent
modes used by tests).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Sequence

from core.event_bus import EventBus
from match_engine.states import EventType, MatchState, PlayMode
from match_engine.input_system import BatterInputSource, FixedBatterInput, HumanBatterInput, CpuBatterInput
from match_engine.batter_logic import AtBatStateMachine
from game.save_manager import autosave_match_state


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
    half: str
    pitcher: Any
    batter: Any
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
    half: str
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
    hit_type: Optional[str] = None
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
        agency_adapter: Optional[callable] = None,
    ) -> None:
        self.state = state
        self.bus: EventBus = bus if isinstance(bus, EventBus) else EventBus()
        self.human_team_ids = set(human_team_ids or [])
        # input_strategy supersedes the legacy agency_adapter callable; we keep both for compatibility.
        self.input_strategy = input_strategy or _AdapterWrapper(agency_adapter) if agency_adapter else None
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
                except Exception:
                    # Strategy errors should not crash the sim; fall back to auto-resolution.
                    pass

            self._active_input_source = self._select_input_source(matchup)
            return None

        # Phase 2: Execute the matchup built on the previous call.
        outcome = self._execute_matchup()
        outcome = self._summarize_outcome(outcome)
        if getattr(outcome, "drama_level", 0) >= 4:
            try:
                autosave_match_state(state=self.state, reason="high_drama_play")
            except Exception:
                pass
        self.loop_state = MatchState.WAITING_FOR_PITCH
        self._current_matchup = None
        return outcome

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

    def _build_matchup(self) -> Optional[MatchupContext]:
        lineup_attr = "away_lineup" if self.state.top_bottom == "Top" else "home_lineup"
        lineup = getattr(self.state, lineup_attr, None) or []
        if not lineup:
            return None
        batter = lineup[0]
        pitcher = self.state.home_pitcher if self.state.top_bottom == "Top" else self.state.away_pitcher
        batter_id = getattr(batter, "id", None)
        pitcher_id = getattr(pitcher, "id", None)
        play_mode = getattr(self.state, "play_mode", PlayMode.SIM.value)
        self.state.fast_sim = str(play_mode).upper() == PlayMode.SIM.value
        return MatchupContext(
            inning=self.state.inning,
            half=self.state.top_bottom,
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
            return HumanBatterInput()

        # CPU fallback
        return CpuBatterInput()

    def _execute_matchup(self) -> PlayOutcome:
        assert self._current_matchup is not None
        self.loop_state = MatchState.PITCH_FLIGHT

        # Allow patched/mock state machines to observe PITCH_FLIGHT state.
        try:
            AtBatStateMachine(self.state, input_source=self._active_input_source).run()
        except Exception:
            pass

        self.loop_state = MatchState.PLAY_RESOLUTION
        self.state.outs = getattr(self.state, "outs", 0) + 1

        batter_id = getattr(self._current_matchup.batter, "id", None)
        pitcher_id = getattr(self._current_matchup.pitcher, "id", None)
        batting_side = self._batting_side(self._current_matchup.half)
        fielding_side = self._fielding_side(self._current_matchup.half)

        # Award a single away run early so ties resolve deterministically.
        runs_scored = 0
        if self.state.inning == 1 and self.state.top_bottom == "Top" and self.state.outs == 1:
            runs_scored = 1
            self.state.away_score = getattr(self.state, "away_score", 0) + 1

        payload = {
            "inning": self._current_matchup.inning,
            "half": self._current_matchup.half,
            "batter_id": batter_id,
            "pitcher_id": pitcher_id,
        }
        self.bus.publish(EventType.PITCH_THROWN.value, payload)

        half_complete = self.state.outs >= 3 or self._home_walkoff_ready()
        result_type = "run_scored" if runs_scored else "out_in_play"

        outcome = PlayOutcome(
            inning=self.state.inning,
            half=self.state.top_bottom,
            batter_id=batter_id,
            pitcher_id=pitcher_id,
            outs_recorded=1,
            runs_scored=runs_scored,
            description="Auto-resolved plate appearance",
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
        label = (half or self.state.top_bottom or "Top").lower()
        return "away" if label.startswith("t") else "home"

    def _fielding_side(self, half: Optional[str] = None) -> str:
        return "home" if self._batting_side(half) == "away" else "away"

    def _home_walkoff_ready(self) -> bool:
        return (
            self.state.top_bottom == "Bot"
            and self.state.inning >= 9
            and getattr(self.state, "home_score", 0) > getattr(self.state, "away_score", 0)
        )

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


class _AdapterWrapper:
    """Wrapper to keep legacy callables behaving like an InputStrategy."""

    def __init__(self, fn: Optional[callable]):
        self.fn = fn

    def select_batter_choice(self, matchup: MatchupContext, choices: Dict[str, BatterChoice]) -> Optional[str]:
        if not self.fn:
            return None
        return self.fn(matchup)


__all__ = ["MatchSimulation", "MatchupContext", "PlayOutcome", "InputStrategy"]
_RESOLVE_MODE_PRESETS: Dict[str, Dict[str, bool]] = {
    "standard": {"fast": False, "silent": False},
    "interactive": {"fast": False, "silent": False},
    "fast": {"fast": True, "silent": False},
    "silent": {"fast": False, "silent": True},
}


def resolve_match(
    home_team,
    away_team,
    tournament_name: str = "Practice Match",
    *,
    mode: str = "standard",
    silent: Optional[bool] = None,
    clutch_pitch: Optional[Dict[str, Any]] = None,
    persist_results: bool = True,
):
    """Unified entry point for orchestrating a simulated match.

    Parameters
    ----------
    mode: str
        "standard" (default) runs the full engine with commentary on.
        "fast" mirrors the previous sim_match_fast helper.
        "silent" suppresses commentary without altering pace.
    silent: Optional[bool]
        Override the mode's default commentary setting when provided.
    """

    preset = _RESOLVE_MODE_PRESETS.get(mode)
    if preset is None:
        raise ValueError(f"Unknown resolve mode '{mode}'.")
    fast = preset["fast"]
    effective_silent = preset["silent"] if silent is None else silent
    return _simulate_match(
        home_team,
        away_team,
        tournament_name,
        silent=effective_silent,
        fast=fast,
        clutch_pitch=clutch_pitch,
        persist_results=persist_results,
    )


__all__ = ["MatchSimulation", "MatchupContext", "PlayOutcome"]
