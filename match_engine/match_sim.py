"""Event-driven match simulation utilities and legacy bridge helpers."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.event_bus import EventBus
from match_engine.batter_logic import AtBatStateMachine
from match_engine.pitch_logic import get_arsenal, get_current_catcher, get_last_pitch_call
from match_engine.pitch_definitions import PITCH_TYPES
from game.scouting_system import get_scouting_info
from game.save_manager import autosave_match_state
from match_engine.states import EventType, MatchState, PlayMode
from player_roles import batter_controls as batter_ui
from battery_system.battery_trust import (
    get_trust_snapshot,
    set_trust_snapshot,
    trust_delta_for_plate_result,
)

from .momentum import MomentumSystem


@dataclass
class BatterChoice:
    """Represents a Batter's Eye selection."""

    key: str
    label: str
    action: str
    mods: Dict[str, int]
    guess_payload: Optional[Dict[str, Any]] = None
    description: str = ""


@dataclass
class MatchupContext:
    """Snapshot of the matchup context before the pitch is resolved."""

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
    batter_stats: Dict[str, int]
    pitcher_stats: Dict[str, int]
    is_human: bool


@dataclass
class PlayOutcome:
    """Public summary describing how a play resolved."""

    inning: int
    half: str
    batter_id: Optional[int]
    pitcher_id: Optional[int]
    outs_recorded: int
    runs_scored: int
    description: str
    result_type: str
    half_complete: bool
    drama_level: int
    batting_team: str
    fielding_team: str
    hit_type: Optional[str] = None
    double_play: bool = False
    error_on_play: bool = False
    error_type: Optional[str] = None
    error_position: Optional[str] = None


class MatchSimulation:
    """Single at-bat micro state machine that publishes EventBus updates."""

    _CHOICE_LIBRARY: Dict[str, BatterChoice] = {
        "fastball": BatterChoice(
            key="fastball",
            label="Sit on Fastball",
            action="Power",
            mods={"contact_mod": -5, "power_mod": 15, "eye_mod": -5},
            guess_payload={"kind": "family", "value": "fastball", "label": "Fastball", "source": "user"},
            description="Adds lift vs heat; risky if the pitcher spins it.",
        ),
        "breaker": BatterChoice(
            key="breaker",
            label="Sit on Breaking",
            action="Contact",
            mods={"contact_mod": 12, "power_mod": -10, "eye_mod": -4},
            guess_payload={"kind": "family", "value": "breaker", "label": "Breaking Ball", "source": "user"},
            description="Stay back and shoot the gap when spin hangs.",
        ),
        "react": BatterChoice(
            key="react",
            label="React",
            action="Normal",
            mods={"contact_mod": 0, "power_mod": 0, "eye_mod": 0},
            guess_payload=None,
            description="Trust your eyes and play it straight.",
        ),
    }

    def __init__(
        self,
        state,
        *,
        bus: Optional[EventBus] = None,
        human_team_ids: Optional[Sequence[int]] = None,
        agency_adapter: Optional[Callable[[MatchupContext], str]] = None,
    ) -> None:
        self.state = state
        self.bus = bus or EventBus()
        self.loop_state: MatchState = MatchState.WAITING_FOR_PITCH
        self.human_team_ids = {team_id for team_id in (human_team_ids or []) if team_id is not None}
        self.agency_adapter = agency_adapter
        self.awaiting_player_choice: bool = False
        self._current_matchup: Optional[MatchupContext] = None
        self._pending_choice: Optional[BatterChoice] = None
        self._pending_choice_options: List[Dict[str, str]] = []
        self._trust_buffer: Dict[Tuple[int, int], int] = {}
        self._pending_cut_in: bool = False

    def step(self) -> Optional[PlayOutcome]:
        """Advance the simulation by a single action tick."""

        # If we just fired a cut-in, hold the loop for one tick so UI can animate.
        if self._pending_cut_in:
            self._pending_cut_in = False
            return None

        if self._current_matchup is None:
            self._current_matchup = self._build_matchup()
            if self._current_matchup is None:
                return None

        if self._is_rivalry_moment(self._current_matchup):
            if self._emit_rival_cut_in(self._current_matchup):
                self._pending_cut_in = True
                return None

        if self._current_matchup.is_human and not self._pending_choice:
            if not self.awaiting_player_choice:
                if self._maybe_apply_agent_choice():
                    return None
                self._prompt_player_choice()
            return None

        outcome = self._execute_matchup()
        self._current_matchup = None
        self._pending_choice = None
        self.awaiting_player_choice = False
        self._pending_choice_options.clear()
        self.loop_state = MatchState.WAITING_FOR_PITCH
        return outcome

    def pop_trust_buffer(self) -> Dict[Tuple[int, int], int]:
        """Return and reset the accumulated trust deltas for this simulation."""

        buffer = self._trust_buffer
        self._trust_buffer = {}
        return buffer

    def submit_player_choice(self, choice_key: str) -> None:
        """Accept a Batter's Eye selection from a human player."""

        if choice_key not in self._CHOICE_LIBRARY:
            raise ValueError(f"Unknown Batter's Eye choice '{choice_key}'.")
        self._pending_choice = self._CHOICE_LIBRARY[choice_key]
        self.awaiting_player_choice = False

    def pending_choice_options(self) -> Sequence[Dict[str, str]]:
        return tuple(self._pending_choice_options)

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
        force_sim = str(play_mode).upper() == PlayMode.SIM.value
        self.state.fast_sim = force_sim
        return MatchupContext(
            inning=self.state.inning,
            half=self.state.top_bottom,
            pitcher=pitcher,
            batter=batter,
            lineup_attr=lineup_attr,
            balls=self.state.balls,
            strikes=self.state.strikes,
            outs_before=self.state.outs,
            home_score=self.state.home_score,
            away_score=self.state.away_score,
            batter_stats=self.state.get_stats(batter_id).copy(),
            pitcher_stats=self.state.get_stats(pitcher_id).copy(),
            is_human=(False if force_sim else self._is_user_controlled(batter)),
        )

    def _maybe_apply_agent_choice(self) -> bool:
        if not self.agency_adapter or self._current_matchup is None:
            return False
        choice_key = self.agency_adapter(self._current_matchup)
        if not choice_key:
            return False
        self.submit_player_choice(choice_key)
        return True

    def _prompt_player_choice(self) -> None:
        if self._current_matchup is None:
            return
        self.awaiting_player_choice = True
        hint = self._scouting_hint(self._current_matchup)
        self._pending_choice_options = [
            {
                "key": choice.key,
                "label": choice.label,
                "description": choice.description,
            }
            for choice in self._CHOICE_LIBRARY.values()
        ]
        payload = {
            "inning": self._current_matchup.inning,
            "half": self._current_matchup.half,
            "batter_id": getattr(self._current_matchup.batter, "id", None),
            "options": self._pending_choice_options,
            "hint": hint,
        }
        self.bus.publish(EventType.BATTERS_EYE_PROMPT.value, payload)

    def _scouting_hint(self, matchup: MatchupContext) -> Optional[str]:
        pitcher = matchup.pitcher
        stats = matchup.pitcher_stats or {}
        pitcher_id = getattr(pitcher, "id", None)
        batter_id = getattr(matchup.batter, "id", None)
        velocity = stats.get("velocity", getattr(pitcher, "velocity", 0) or 0)
        movement = stats.get("movement", getattr(pitcher, "movement", 0) or 0)
        control = stats.get("control", getattr(pitcher, "control", 0) or 0)
        aggression = getattr(pitcher, "aggression", 50) or 50

        hints: List[str] = []
        heat_bias = velocity - movement
        spin_bias = movement - velocity
        if heat_bias >= 6:
            hints.append("Fastball leaning; heaters early in counts.")
        elif spin_bias >= 6:
            hints.append("Breaker leaning; expect spin in leverage.")
        else:
            hints.append("Balanced mix; react if unsure.")

        if control >= 65 and aggression >= 55:
            hints.append("Attacks early — hunt first-pitch heater.")
        elif control <= 50:
            hints.append("Erratic — make them earn the zone.")

        if pitcher_id:
            try:
                arsenal = get_arsenal(pitcher_id)
            except Exception:
                arsenal = []
            family_counts: Dict[str, int] = {}
            for pitch in arsenal:
                name = getattr(pitch, "pitch_name", "")
                family = (PITCH_TYPES.get(name) or {}).get("family", "Other")
                family_counts[family] = family_counts.get(family, 0) + 1
            if family_counts:
                top_family = max(family_counts, key=family_counts.get)
                count = family_counts[top_family]
                if count >= max(2, len(arsenal) // 2):
                    hints.append(f"Carries a {top_family.lower()} heavy mix.")
                elif len(family_counts) >= 3:
                    hints.append("Deep mix — stay flexible.")

        last_call = get_last_pitch_call(self.state, pitcher_id, batter_id) if pitcher_id else None
        if last_call:
            family = last_call.get("family") or ""
            pitch_name = last_call.get("pitch_name") or family or "Pitch"
            location = last_call.get("location") or "Zone"
            hints.append(f"Last pitch: {pitch_name} ({family}) to the {location}.")

        try:
            scouting = get_scouting_info(getattr(pitcher, "school_id", getattr(pitcher, "team_id", None)))
            knowledge = getattr(scouting, "knowledge_level", 0) or 0
        except Exception:
            knowledge = 0
        if knowledge >= 3:
            hints.append("Scouting Lv3: opens with strikes; doubles spin when ahead.")
        elif knowledge == 2:
            hints.append("Scouting Lv2: breakers for put-aways; heater early.")
        elif knowledge == 1:
            hints.append("Scouting Lv1: leans heater when behind.")

        return " ".join(hints[:3]) if hints else None

    def _execute_matchup(self) -> PlayOutcome:
        assert self._current_matchup is not None
        matchup = self._current_matchup
        batter_choice = self._pending_choice if matchup.is_human else None
        self.loop_state = MatchState.PITCH_FLIGHT
        rival_plate = False
        ctx = getattr(self.state, "rival_match_context", None)
        if ctx:
            rival_plate = ctx.is_rival_plate(getattr(matchup.batter, "id", None))

        self.bus.publish(
            EventType.PITCH_THROWN.value,
            {
                "inning": matchup.inning,
                "half": matchup.half,
                "pitcher_id": getattr(matchup.pitcher, "id", None),
                "batter_id": getattr(matchup.batter, "id", None),
                "balls": matchup.balls,
                "strikes": matchup.strikes,
                "home_score": matchup.home_score,
                "away_score": matchup.away_score,
                "rival_plate": rival_plate,
            },
        )
        with self._override_player_input(batter_choice):
            AtBatStateMachine(self.state).run()
        outcome = self._summarize_outcome(matchup)
        psych = getattr(self.state, "psychology_engine", None)
        if psych:
            psych.record_plate_outcome(outcome)
        self._update_battery_trust(matchup.pitcher, outcome)
        batting_side = self._batting_side(matchup.half)
        fielding_side = self._fielding_side(matchup.half)
        batting_team_id = self._team_id_for_side(batting_side)
        fielding_team_id = self._team_id_for_side(fielding_side)
        swing_payload = {
            "inning": outcome.inning,
            "half": outcome.half,
            "batter_id": outcome.batter_id,
            "pitcher_id": outcome.pitcher_id,
            "result_type": outcome.result_type,
            "drama_level": outcome.drama_level,
            "batting_team": batting_side,
            "fielding_team": fielding_side,
            "batting_team_id": batting_team_id,
            "fielding_team_id": fielding_team_id,
            "momentum": self._momentum_snapshot(),
        }
        self.loop_state = MatchState.CONTACT_MOMENT
        self.bus.publish(EventType.BATTER_SWUNG.value, swing_payload)
        if outcome.result_type == "strikeout":
            self.bus.publish(EventType.STRIKEOUT.value, swing_payload)
        self.loop_state = MatchState.PLAY_RESOLUTION
        play_detail = getattr(self.state, "latest_play_detail", None) or {}
        self.bus.publish(
            EventType.PLAY_RESULT.value,
            {
                "inning": outcome.inning,
                "half": outcome.half,
                 "pitcher_id": outcome.pitcher_id,
                 "batter_id": outcome.batter_id,
                 "result_type": outcome.result_type,
                "outs_recorded": outcome.outs_recorded,
                "runs_scored": outcome.runs_scored,
                "description": outcome.description,
                "drama_level": outcome.drama_level,
                "batting_team": batting_side,
                "fielding_team": fielding_side,
                "batting_team_id": batting_team_id,
                "fielding_team_id": fielding_team_id,
                "hit_type": play_detail.get("hit_type"),
                "double_play": bool(play_detail.get("double_play")),
                "error_on_play": bool(play_detail.get("error_on_play")),
                "error_type": play_detail.get("error_type"),
                "error_position": play_detail.get("error_position"),
                "momentum": self._momentum_snapshot(),
            },
        )
        self._autosave_checkpoint(reason="play", drama=outcome.drama_level)
        self._rotate_lineup(matchup.lineup_attr)
        return outcome

    def _momentum_snapshot(self) -> Optional[Dict[str, float]]:
        system = getattr(self.state, "momentum_system", None)
        if system and hasattr(system, "serialize"):
            try:
                return system.serialize()
            except Exception:
                return None
        return None

    def _autosave_checkpoint(self, *, reason: str, drama: int = 0) -> None:
        enabled = getattr(self.state, "autosave_enabled", True)
        if not enabled:
            return
        marker_key = f"{self.state.inning}_{self.state.top_bottom}_{self.state.outs}_{reason}"
        markers = getattr(self.state, "autosave_markers", None)
        if not isinstance(markers, set):
            markers = set()
        if marker_key in markers and drama < 2:
            return
        try:
            autosave_match_state(state=self.state, reason=f"{reason}-drama{drama}")
            markers.add(marker_key)
            self.state.autosave_markers = markers
        except Exception:
            # Autosave failures should never block gameplay.
            return

    def _summarize_outcome(self, matchup: MatchupContext) -> PlayOutcome:
        batter_id = getattr(matchup.batter, "id", None)
        pitcher_id = getattr(matchup.pitcher, "id", None)
        batter_stats_after = self.state.get_stats(batter_id)
        pitcher_stats_after = self.state.get_stats(pitcher_id)
        strikeout_delta = pitcher_stats_after["strikeouts_pitched"] - matchup.pitcher_stats["strikeouts_pitched"]
        hit_delta = batter_stats_after["hits"] - matchup.batter_stats["hits"]
        walk_delta = batter_stats_after["walks"] - matchup.batter_stats["walks"]
        offense_runs = (
            self.state.away_score - matchup.away_score
            if matchup.half == "Top"
            else self.state.home_score - matchup.home_score
        )
        outs_recorded = max(0, self.state.outs - matchup.outs_before)
        batting_side = self._batting_side(matchup.half)
        fielding_side = self._fielding_side(matchup.half)
        play_detail = getattr(self.state, "latest_play_detail", None) or {}
        hit_type = play_detail.get("hit_type")
        double_play = bool(play_detail.get("double_play"))
        error_flag = bool(play_detail.get("error_on_play"))
        error_type = play_detail.get("error_type")
        error_position = play_detail.get("error_position")
        result_type = "neutral"
        description = play_detail.get("description")
        if strikeout_delta > 0:
            result_type = "strikeout"
            description = "Blown away on strikes."
        elif double_play:
            result_type = "double_play"
            description = description or "Defenders turn two in style."
        elif offense_runs > 0:
            result_type = "run_scored"
            description = description or f"{offense_runs} run(s) score."
        elif hit_delta > 0:
            result_type = "hit"
            description = description or "Base hit keeps momentum alive."
        elif outs_recorded > 0:
            result_type = "out_in_play"
            description = description or "Defense records the out."
        elif walk_delta > 0:
            result_type = "walk"
            description = "Patient trip to first."
        description = description or "Batter reaches safely."
        drama_level = self._compute_drama_level()
        half_complete = self.state.outs >= 3 or self._home_walkoff_ready()
        return PlayOutcome(
            inning=self.state.inning,
            half=self.state.top_bottom,
            batter_id=batter_id,
            pitcher_id=pitcher_id,
            outs_recorded=outs_recorded,
            runs_scored=offense_runs,
            description=description,
            result_type=result_type,
            half_complete=half_complete,
            drama_level=drama_level,
            batting_team=batting_side,
            fielding_team=fielding_side,
            hit_type=hit_type,
            double_play=double_play,
            error_on_play=error_flag,
            error_type=error_type,
            error_position=error_position,
        )

    def _update_battery_trust(self, pitcher, outcome: PlayOutcome) -> None:
        catcher = get_current_catcher(self.state)
        pitcher_id = getattr(pitcher, "id", None)
        catcher_id = getattr(catcher, "id", None)
        if not pitcher_id or not catcher_id:
            return
        delta = trust_delta_for_plate_result(
            result_type=outcome.result_type,
            hit_type=outcome.hit_type,
        )
        if delta == 0:
            return
        key = (pitcher_id, catcher_id)
        self._trust_buffer[key] = self._trust_buffer.get(key, 0) + delta
        current_value = get_trust_snapshot(self.state, pitcher_id, catcher_id)
        set_trust_snapshot(self.state, pitcher_id, catcher_id, current_value + delta)

    def _batting_side(self, half: Optional[str] = None) -> str:
        label = (half or self.state.top_bottom or "Top").lower()
        return "away" if label.startswith("t") else "home"

    def _fielding_side(self, half: Optional[str] = None) -> str:
        return "home" if self._batting_side(half) == "away" else "away"

    def _team_id_for_side(self, side: Optional[str]) -> Optional[int]:
        if side == "home":
            return getattr(self.state.home_team, "id", None)
        if side == "away":
            return getattr(self.state.away_team, "id", None)
        return None

    def _rotate_lineup(self, lineup_attr: str) -> None:
        lineup = getattr(self.state, lineup_attr, None)
        if not lineup or len(lineup) <= 1:
            return
        lineup[:] = lineup[1:] + lineup[:1]

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

    def _compute_drama_level(self) -> int:
        inning = self.state.inning
        score_gap = abs(self.state.home_score - self.state.away_score)
        level = 0
        if inning >= 7:
            level += 1
        if score_gap <= 2:
            level += 1
        if inning >= 9 and score_gap <= 1:
            level += 1
        return min(level, 3)

    @contextmanager
    def _override_player_input(self, choice: Optional[BatterChoice]):
        if not choice or not (self._current_matchup and self._current_matchup.is_human):
            yield
            return

        original = batter_ui.player_bat_turn

        def _proxy(*_):  # pragma: no cover - executed via gameplay
            mods = dict(choice.mods)
            if choice.guess_payload:
                mods["guess_payload"] = dict(choice.guess_payload)
            return choice.action, mods

        batter_ui.player_bat_turn = _proxy
        try:
            yield
        finally:
            batter_ui.player_bat_turn = original

    def _is_user_controlled(self, player: Any) -> bool:
        team_id = getattr(player, "team_id", getattr(player, "school_id", None))
        if getattr(player, "is_user_controlled", False):
            return True
        if team_id is None:
            return False
        return team_id in self.human_team_ids

    def _home_walkoff_ready(self) -> bool:
        return (
            self.state.top_bottom == "Bot"
            and self.state.inning >= 9
            and self.state.home_score > self.state.away_score
        )


@contextmanager
def _suppress_print():
    """Temporarily silence stdout for background simulations."""

    original_stdout = sys.stdout
    devnull = open(os.devnull, "w", encoding="utf-8")
    try:
        sys.stdout = devnull
        yield
    finally:
        sys.stdout = original_stdout
        devnull.close()


def _fetch_latest_score(home_id: int, away_id: int, tournament_name: str) -> str:
    """Read the latest game for the two teams and optionally tag the tournament."""

    from database.setup_db import Game, session_scope

    score_str = "0 - 0"
    try:
        with session_scope() as session:
            game = (
                session.query(Game)
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
                session.commit()
    except Exception:
        return "Error"

    return score_str


def _simulate_match(
    home_team,
    away_team,
    tournament_name: str,
    *,
    silent: bool,
    fast: bool,
    clutch_pitch: Optional[Dict[str, Any]] = None,
    persist_results: bool = True,
):
    from database.setup_db import session_scope
    from game.coach_strategy import consume_strategy_mods
    from .controller import run_match as engine_run_match

    if fast:
        winner = engine_run_match(
            home_team.id,
            away_team.id,
            fast=True,
            persist_results=persist_results,
            clutch_pitch=clutch_pitch,
            tournament_name=tournament_name,
        )
    elif silent:
        with _suppress_print():
            winner = engine_run_match(
                home_team.id,
                away_team.id,
                clutch_pitch=clutch_pitch,
                tournament_name=tournament_name,
                persist_results=persist_results,
            )
    else:
        winner = engine_run_match(
            home_team.id,
            away_team.id,
            clutch_pitch=clutch_pitch,
            tournament_name=tournament_name,
            persist_results=persist_results,
        )

    score_str = _fetch_latest_score(home_team.id, away_team.id, tournament_name)
    with session_scope() as session:
        consume_strategy_mods(session, home_team.id)
        consume_strategy_mods(session, away_team.id)
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


__all__ = ["MatchSimulation", "PlayOutcome", "resolve_match"]
