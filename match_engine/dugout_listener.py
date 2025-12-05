from __future__ import annotations

from typing import Dict, Optional

from core.event_bus import EventBus
from match_engine.states import EventType
from match_engine.psychology import PsychologyEngine


class DugoutListener:
    """Translates raw engine events into dugout chatter and story beats."""

    def __init__(
        self,
        state,
        *,
        bus: EventBus,
        psychology: Optional[PsychologyEngine] = None,
    ) -> None:
        self.state = state
        self.bus = bus
        self.psychology = psychology
        self._flags: Dict[str, int] = {}
        bus.subscribe(EventType.PITCH_THROWN.value, self._handle_pitch)
        bus.subscribe(EventType.BATTER_SWUNG.value, self._handle_swing)
        bus.subscribe(EventType.PLAY_RESULT.value, self._handle_play)

    def _emit(self, message: str, *, tag: str = "General", **meta) -> None:
        logs = getattr(self.state, "logs", None)
        if isinstance(logs, list):
            logs.append(message)
        payload = {
            "message": message,
            "tag": tag,
            "inning": getattr(self.state, "inning", 1),
            "half": getattr(self.state, "top_bottom", "Top"),
        }
        payload.update(meta)
        self.bus.publish(EventType.DUGOUT_CHATTER.value, payload)

    def _cooldown_key(self, key: str) -> str:
        return f"{key}-inning-{self.state.inning}"

    def _handle_pitch(self, payload: Dict[str, object]) -> None:
        pitcher_id = payload.get("pitcher_id")
        if not pitcher_id or not self.psychology:
            return
        snapshot = self.psychology.pitcher_modifiers(pitcher_id)
        if snapshot.trauma < 4:
            return
        flag = self._cooldown_key(f"trauma-{pitcher_id}")
        if flag in self._flags:
            return
        self._flags[flag] = self.state.inning
        pitcher = getattr(self.state, "player_lookup", {}).get(pitcher_id)
        name = getattr(pitcher, "last_name", getattr(pitcher, "name", "Pitcher"))
        self._emit(
            f"[Dugout] {name} looks shaken after that last rocket. Coaches motion for deeper breaths.",
            tag="Pitching",
            pitcher_id=pitcher_id,
            trauma=snapshot.trauma,
        )

    def _handle_swing(self, payload: Dict[str, object]) -> None:
        batter_id = payload.get("batter_id")
        if not batter_id:
            return
        ctx = getattr(self.state, "rival_match_context", None)
        if ctx and ctx.is_rival_plate(batter_id):
            key = self._cooldown_key(f"rival-{batter_id}")
            if key in self._flags:
                return
            self._flags[key] = self.state.inning
            batter = getattr(self.state, "player_lookup", {}).get(batter_id)
            name = getattr(batter, "last_name", getattr(batter, "name", "Rival"))
            self._emit(
                f"[Rivalry] {name} steps in and the dugout tenses — staff calls for a scouting reminder.",
                tag="Rivalry",
                batter_id=batter_id,
            )

    def _handle_play(self, payload: Dict[str, object]) -> None:
        runs = payload.get("runs_scored", 0)
        drama = payload.get("drama_level", 1)
        batting_team = payload.get("batting_team")
        if runs:
            key = self._cooldown_key(f"runs-{batting_team}")
            if key not in self._flags or self._flags[key] != self.state.inning:
                self._flags[key] = self.state.inning
                side = "home" if batting_team == "home" else "away"
                self._emit(
                    f"[Momentum] {runs} run(s) score for the {side} dugout; helmets fly as energy spikes.",
                    tag="Momentum",
                    runs=runs,
                    drama=drama,
                )
        if self.psychology and payload.get("result_type") == "strikeout":
            pitcher_id = payload.get("pitcher_id")
            snapshot = self.psychology.pitcher_modifiers(pitcher_id)
            if snapshot.focus >= 3:
                key = self._cooldown_key(f"ace-{pitcher_id}")
                if key in self._flags:
                    return
                self._flags[key] = self.state.inning
                pitcher = getattr(self.state, "player_lookup", {}).get(pitcher_id)
                name = getattr(pitcher, "last_name", getattr(pitcher, "name", "Pitcher"))
                self._emit(
                    f"[Dugout] {name} stalks off the mound with glare locked in — dugout feeds the fire.",
                    tag="Pitching",
                    pitcher_id=pitcher_id,
                    focus=snapshot.focus,
                )


__all__ = ["DugoutListener"]
