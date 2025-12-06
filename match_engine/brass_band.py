from __future__ import annotations

import random
from typing import Optional

from core.event_bus import EventBus
from match_engine.states import EventType

SILENCE_SOUNDS = [
    "(Ambience) Wind blows through the empty stands...",
    "(Sound) Scattered clapping from a few parents.",
    "(Sound) 'Hang in there!' a lone voice yells.",
    "(Ambience) The umpire's call echoes loudly.",
]

CHANT_SOUNDS = [
    "♪ (Chant) 'FIGHT! FIGHT! FIGHT!' ♪",
    "♪ (Rhythm) CLAP... CLAP... CLAP-CLAP-CLAP! ♪",
    "♪ (Megaphones) 'Let's go [Team Name], Let's go!' ♪",
    "(Sound) The alumni section is making some noise.",
]

BAND_SOUNDS = {
    "NEUTRAL": "♪ (Brass) 'School Anthem' (March Ver.) ♪",
    "CHANCE": "♪♪ (Trumpet) 'Sniper's Sight' is blaring! ♪♪",
    "FRENZY": "♫♫ (Band) The stands are rocking to 'Meteor Strike'! ♫♫",
    "PINCH": "(Pressure) The enemy band is drowning us out...",
}

ELITE_SOUNDS = {
    "NEUTRAL": "♫♫ (Symphony) The massive band plays 'Glory Bound' in perfect unison! ♫♫",
    "CHANCE": "♫♫ (Roar) 200 members strong! 'Savage Impact' shakes the ground! ♫♫",
    "FRENZY": "♫♫ (Climax) THE STADIUM IS ALIVE! 'Final Legend' at MAX VOLUME! ♫♫",
    "PINCH": "(Despair) The sheer volume of the enemy support is crushing...",
}


class BrassBand:
    """Adaptive dugout audio cues that respond to prestige, momentum, and walk-up themes."""

    def __init__(self, state) -> None:
        self.state = state
        self.bus: Optional[EventBus] = getattr(state, "event_bus", None)
        self.current_song: Optional[str] = None
        self.last_batter_id: Optional[int] = None
        self.support_tier = self._calculate_support_tier(getattr(state, "home_team", None))
        if self.bus:
            self.bus.subscribe(EventType.MATCH_STATE.value, self.on_state_change)
            self.bus.subscribe(EventType.MOMENTUM_SHIFT.value, self.on_momentum)

    # --- tier logic -------------------------------------------------
    def _calculate_support_tier(self, school) -> int:
        if not school:
            return 0
        tourney = (
            getattr(self.state, "tournament", None)
            or getattr(self.state, "tournament_name", "")
            or ""
        )
        if "koshien" in str(tourney).lower():
            return 3
        prestige = getattr(school, "prestige", 0) or 0
        era = getattr(school, "current_era", "REBUILDING") or "REBUILDING"
        tier = 0
        if prestige >= 20:
            tier = 1
        if prestige >= 45:
            tier = 2
        if prestige >= 75:
            tier = 3
        if era == "DARK_HORSE":
            tier = min(3, tier + 1)
        elif era == "SLEEPING_LION":
            tier = max(1, tier - 1)
        return tier

    # --- event hooks ------------------------------------------------
    def on_state_change(self, payload):  # pragma: no cover - driven by gameplay
        if payload.get("state") != "STATE_WINDUP":
            return
        batter_id = payload.get("batter_id")
        if batter_id is None or batter_id == self.last_batter_id:
            return
        self.last_batter_id = batter_id
        self._handle_walkup(batter_id)

    def on_momentum(self, _payload):  # pragma: no cover - driven by gameplay
        if self.current_song and "Theme" in self.current_song:
            return
        mood = self._current_mood()
        self._play_context_music(mood)

    # --- mood + playback --------------------------------------------
    def _current_mood(self) -> str:
        system = getattr(self.state, "momentum_system", None)
        meter = getattr(system, "meter", 0.0) if system else 0.0
        if meter >= 12:
            return "FRENZY"
        if meter >= 4:
            return "CHANCE"
        if meter <= -8:
            return "PINCH"
        return "NEUTRAL"

    def _play_context_music(self, mood: str) -> None:
        if self.support_tier == 0:
            if random.random() < 0.15:
                self._publish_song(random.choice(SILENCE_SOUNDS), "DIM")
            return
        if self.support_tier == 1:
            if random.random() < 0.2:
                team_name = getattr(self.state.home_team, "name", "Team")
                raw = random.choice(CHANT_SOUNDS)
                text = raw.replace("[Team Name]", team_name)
                self._publish_song(text, "DIM")
            return
        sound_bank = ELITE_SOUNDS if self.support_tier == 3 else BAND_SOUNDS
        text = sound_bank.get(mood, sound_bank.get("NEUTRAL"))
        color = "YELLOW" if self.support_tier == 3 else "CYAN"
        if mood == "NEUTRAL":
            color = "DIM"
        self._publish_song(text, color)

    def _handle_walkup(self, batter_id: int) -> None:
        players = getattr(self.state, "player_lookup", {}) or {}
        player = players.get(batter_id)
        if not player:
            return
        team_map = getattr(self.state, "player_team_map", {}) or {}
        team_id = team_map.get(batter_id)
        user_team_id = getattr(self.state.home_team, "id", None)
        has_theme = getattr(player, "theme_song", None)
        if has_theme and self.support_tier >= 2:
            if team_id != user_team_id and self.support_tier < 3:
                return
            player_name = getattr(player, "last_name", getattr(player, "name", "Batter"))
            prefix = "♫♫ (Orchestra)" if self.support_tier == 3 else "♪♪ (Band)"
            text = f"{prefix} {player_name}'s Theme '{has_theme}' begins! {prefix}"
            self._publish_song(text, "PERSONAL")
            return
        mood = self._current_mood()
        self._play_context_music(mood)

    def _publish_song(self, text: Optional[str], style: str) -> None:
        if not text or text == self.current_song:
            return
        self.current_song = text
        logs = getattr(self.state, "logs", None)
        if isinstance(logs, list):
            logs.append(text)
        if self.bus:
            self.bus.publish("COMMENTARY_LOG", {"text": text, "color": style})


__all__ = ["BrassBand"]
