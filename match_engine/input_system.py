from typing import Any, Callable, Dict, Optional, Protocol, Tuple

from core.io_interface import IOInterface
from match_engine.batter_logic import _apply_offense_orders, _auto_batters_eye_guess


class BatterInputSource(Protocol):
    def get_batting_decision(self, context: Any) -> Tuple[str, Dict[str, Any]]:
        """Return (action_name, modifiers_dict) given the current at-bat context."""
        ...


class HumanBatterInput:
    """Human-controlled batter input using existing UI prompts."""

    def __init__(
        self,
        io: Optional[IOInterface] = None,
        handler: Optional[Callable[[Any, Any, Any, Optional[IOInterface]], Tuple[str, Dict[str, Any]]]] = None,
    ) -> None:
        self.io = io
        resolved = handler or getattr(io, "batter_handler", None) or getattr(io, "player_bat_turn", None)
        if resolved is None:
            raise RuntimeError("HumanBatterInput requires a batting handler; provide handler or set io.batter_handler")
        self.handler = resolved

    def get_batting_decision(self, context: Any) -> Tuple[str, Dict[str, Any]]:
        pitcher = context.get("pitcher")
        batter = context.get("batter")
        state = context.get("state")
        return self.handler(pitcher, batter, state, io=self.io)


class FixedBatterInput:
    """Return a predetermined choice to bypass interactive input."""

    def __init__(self, choice):
        self.choice = choice

    def get_batting_decision(self, context: Any) -> Tuple[str, Dict[str, Any]]:
        mods = dict(self.choice.mods)
        if getattr(self.choice, "guess_payload", None):
            mods["guess_payload"] = dict(self.choice.guess_payload)
        return self.choice.action, mods


class CpuBatterInput:
    """Simple CPU strategy using existing offense orders/auto logic hooks."""

    def get_batting_decision(self, context: Any) -> Tuple[str, Dict[str, Any]]:
        batter_action = "Normal"
        batter_mods: Dict[str, Any] = {}
        state = context.get("state")
        batter = context.get("batter")
        pitcher = context.get("pitcher")
        batter_tendencies = context.get("batter_tendencies")
        offense_order = context.get("offense_order")

        batter_action, batter_mods = _apply_offense_orders(offense_order, state, batter_action, batter_mods)
        guess_payload = _auto_batters_eye_guess(state, batter, pitcher, batter_tendencies)
        if guess_payload:
            batter_mods["guess_payload"] = guess_payload
        return batter_action, batter_mods
