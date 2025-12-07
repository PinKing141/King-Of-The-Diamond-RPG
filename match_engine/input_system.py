from typing import Any, Dict, Protocol, Tuple

from player_roles import batter_controls as batter_ui


class BatterInputSource(Protocol):
    def get_batting_decision(self, context: Any) -> Tuple[str, Dict[str, Any]]:
        """Return (action_name, modifiers_dict) given the current at-bat context."""
        ...


class HumanBatterInput:
    """Human-controlled batter input using existing UI prompts."""

    def get_batting_decision(self, context: Any) -> Tuple[str, Dict[str, Any]]:
        pitcher = context.get("pitcher")
        batter = context.get("batter")
        state = context.get("state")
        return batter_ui.player_bat_turn(pitcher, batter, state)


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

        from match_engine.batter_logic import _apply_offense_orders, _auto_batters_eye_guess

        batter_action, batter_mods = _apply_offense_orders(offense_order, state, batter_action, batter_mods)
        guess_payload = _auto_batters_eye_guess(state, batter, pitcher, batter_tendencies)
        if guess_payload:
            batter_mods["guess_payload"] = guess_payload
        return batter_action, batter_mods
