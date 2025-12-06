from __future__ import annotations

from typing import Dict, Optional

from core.event_bus import EventBus
from match_engine.states import EventType
from match_engine.psychology import PsychologyEngine
from game.rng import get_rng


CHATTER_DB = {
    "PITCH_THROWN": [
        "Nice ball!",
        "Good height!",
        "Low and away, nice course!",
        "That's your best ball!",
        "Make him hit it!",
        "One out, one out!",
        "Let the defense work for you!",
        "Believe in your backstop!",
        "Nice motion!",
        "Keep it low, keep it low!",
        "Don't aim, just throw!",
        "Your pace, Ace! Your pace!",
        "He's watching it! Punish him!",
        "Attacking the zone! I like it!",
        "Nice sound on that mitt!",
        "Shoulders relaxed, just like practice!",
        "One pitch at a time!",
        "Focus on the glove!",
        "He can't touch that heat!",
        "Best pitch of the day!",
        "Nice spin!",
        "Defense is ready!",
        "Ground ball, double play!",
        "Make him fish!",
        "Don't mind the runner!",
        "Batter is scared of you!",
        "Dominate the mound!",
        "NICE BALL!!!",
        "Keep attacking!",
        "Paint that corner!",
    ],
    "STRIKEOUT": [
        "Sit down!",
        "Nice pitch, Ace!",
        "He couldn't touch that!",
        "Way to battle!",
        "That's our Ace!",
        "K!!!!",
        "Looking good up there!",
        "Total shutdown!",
        "He was frozen!",
        "Swinging at air!",
        "That slider was nasty!",
        "Another one down!",
        "Keep that momentum!",
        "They can't see the ball!",
        "Untouchable!",
        "Three pitches, three strikes, see ya!",
        "What a finish!",
        "Monster pitch!",
        "Roar, Ace! Roar!",
        "That's how we start an inning!",
    ],
    "WALK": [
        "Don't mind, don't mind!",
        "Shake it off!",
        "Focus on the next one!",
        "One out helps!",
        "Set up the double play!",
        "Cut the count!",
        "Trust your defense, we'll stop 'em!",
        "Take a breath!",
        "Don't rush!",
        "The runner doesn't matter!",
        "Batter is next!",
        "Reset, reset!",
        "Keep your head up!",
        "It was a good course, ump missed it!",
        "Just a little high, bring it down!",
        "Don't let him get in your head!",
        "Next batter is an easy out!",
        "We'll get it back!",
        "Switch gears!",
        "Calm down!",
    ],
    "RIVAL_FACE_OFF": [
        "CRUSH HIM!",
        "Don't lose to him!",
        "Show him who the real Ace is!",
        "This is the moment!",
        "Send it to the stands!",
        "Don't back down!",
        "Challenge him with the heater!",
        "Break his spirit!",
        "He's been talking, shut him up!",
        "This is YOUR mound!",
        "Maximum power!",
        "Don't let him touch it!",
        "Aim for the strikeout!",
        "Win this battle!",
        "GUTS! SHOW ME YOUR GUTS!",
        "For the team!",
        "Everything you've got!",
        "Become a legend right here!",
        "Stare him down!",
        "Make him regret stepping in the box!",
    ],
    "BATTER_UP": [
        "Send it for a ride!",
        "Find a gap!",
        "Connect!",
        "Just meet the ball!",
        "Eye on the ball!",
        "Don't swing at trash!",
        "Wait for your pitch!",
        "Be the hero!",
        "One hit changes everything!",
        "Keep the line moving!",
        "Sacrifice is fine, just advance him!",
        "Look at the pitcher, he's tired!",
        "Smash it!",
        "Bring 'em home!",
        "Batting practice speed!",
        "He's shaking, he's scared!",
        "Good eye!",
        "Make him throw strikes!",
        "Get on base any way you can!",
        "Do it for the seniors!",
    ],
    "DEFENSE_CHATTER": [
        "Balls to me!",
        "Watch the steal!",
        "Cover first!",
        "Two outs, play at one!",
        "Back up the throw!",
        "Talk to each other!",
        "Gap is open, shift left!",
        "Keep your feet moving!",
        "Ready position!",
        "Don't let it bounce!",
        "Charge the ball!",
        "Crow hop and throw!",
        "Nice scoop!",
        "Way to block it, Catcher!",
        "Pitcher is fielding too!",
        "Watch the bunt!",
        "Infield fly rule is on!",
        "No doubles!",
        "Protect the line!",
        "Play deep!",
    ],
}


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
        self.rng = get_rng()
        self._flags: Dict[str, int] = {}
        bus.subscribe(EventType.PITCH_THROWN.value, self._handle_pitch)
        bus.subscribe(EventType.BATTER_SWUNG.value, self._handle_swing)
        bus.subscribe(EventType.PLAY_RESULT.value, self._handle_play)
        bus.subscribe(EventType.RIVAL_CUT_IN.value, self._handle_cut_in)

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

    def _mark_once(self, key: str) -> bool:
        token = self._cooldown_key(key)
        if self._flags.get(token) == self.state.inning:
            return False
        self._flags[token] = self.state.inning
        return True

    def _team_side_for_player(self, player_id: Optional[int]) -> Optional[str]:
        if not player_id:
            return None
        team_map = getattr(self.state, "player_team_map", {}) or {}
        team_id = team_map.get(player_id)
        if team_id == getattr(self.state.home_team, "id", None):
            return "home"
        if team_id == getattr(self.state.away_team, "id", None):
            return "away"
        return None

    def _side_label(self, side: Optional[str]) -> str:
        if side == "home":
            return getattr(self.state.home_team, "name", "Home")
        if side == "away":
            return getattr(self.state.away_team, "name", "Away")
        return "Dugout"

    def _random_line(self, category: str) -> Optional[str]:
        choices = CHATTER_DB.get(category)
        if not choices:
            return None
        return self.rng.choice(choices)

    def _shout(
        self,
        category: str,
        *,
        tag: str = "General",
        side: Optional[str] = None,
        extra: Optional[str] = None,
        default: Optional[str] = None,
        **meta,
    ) -> None:
        line = self._random_line(category) or default
        if not line:
            return
        if extra:
            line = f"{line} {extra}"
        prefix = f"[{self._side_label(side)} Dugout]"
        if line.startswith("["):
            message = line
        else:
            message = f"{prefix} {line}"
        self._emit(message, tag=tag, **meta)

    def _handle_pitch(self, payload: Dict[str, object]) -> None:
        pitcher_id = payload.get("pitcher_id")
        if not pitcher_id:
            return
        side = self._team_side_for_player(pitcher_id)
        if side and self.rng.random() < 0.55:
            self._shout("PITCH_THROWN", tag="Pitching", side=side, pitcher_id=pitcher_id)
        if not self.psychology:
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
        batting_side = payload.get("batting_team")
        if batter_id and batting_side and self._mark_once(f"batup-{batter_id}"):
            self._shout("BATTER_UP", tag="Offense", side=batting_side, batter_id=batter_id)
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
            extra = f"({name} steps in.)" if name else None
            self._shout(
                "RIVAL_FACE_OFF",
                tag="Rivalry",
                side=batting_side,
                batter_id=batter_id,
                extra=extra,
            )

    def _handle_cut_in(self, payload: Dict[str, object]) -> None:
        batter_id = payload.get("batter_id")
        pitcher_id = payload.get("pitcher_id")
        inning = payload.get("inning")
        half = payload.get("half")
        hero = payload.get("hero_name") or "Hero"
        rival = payload.get("rival_name") or "Rival"
        msg = f"[Cut-In] {hero} vs {rival} — tension spikes as the showdown begins."
        self._emit(
            msg,
            tag="Rivalry",
            inning=inning,
            half=half,
            batter_id=batter_id,
            pitcher_id=pitcher_id,
            pause=True,
        )

    def _handle_play(self, payload: Dict[str, object]) -> None:
        runs = payload.get("runs_scored", 0)
        drama = payload.get("drama_level", 1)
        batting_team = payload.get("batting_team")
        fielding_team = payload.get("fielding_team")
        result_type = payload.get("result_type")
        pitcher_id = payload.get("pitcher_id")
        if result_type == "strikeout" and fielding_team:
            self._shout("STRIKEOUT", tag="Pitching", side=fielding_team, pitcher_id=pitcher_id)
        if result_type == "walk" and fielding_team:
            self._shout("WALK", tag="Pitching", side=fielding_team, pitcher_id=pitcher_id)
        if result_type == "out_in_play" and fielding_team and self.rng.random() < 0.7:
            if self._mark_once(f"defense-{fielding_team}-{self.state.outs}"):
                self._shout("DEFENSE_CHATTER", tag="Defense", side=fielding_team)
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
        if self.psychology and result_type == "strikeout":
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


__all__ = ["DugoutListener", "CHATTER_DB"]
