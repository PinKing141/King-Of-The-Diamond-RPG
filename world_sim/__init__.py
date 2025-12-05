"""World simulation helper exports.

The module avoids importing heavy submodules (which depend on match_engine) at
import time to keep circular dependencies manageable.  Callers can keep using
``from world_sim import foo``; attributes are loaded lazily on first access.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
	"process_npc_growth",
	"simulate_background_matches",
	"run_koshien_tournament",
	"RunnerThreatState",
	"SlideStepResult",
	"StealOutcome",
	"PickoffOutcome",
	"prepare_runner_state",
	"evaluate_slide_step",
	"resolve_steal_attempt",
	"simulate_pickoff",
	"note_runner_pressure",
	"BattedBall",
	"FielderSnapshot",
	"FieldingPlayResult",
	"simulate_batted_ball",
	"build_defense_alignment",
	"resolve_fielding_play",
]

_MODULE_ATTRS = {
	"process_npc_growth": "world_sim.npc_team_ai",
	"simulate_background_matches": "world_sim.prefecture_engine",
	"run_koshien_tournament": "world_sim.tournament_sim",
	"RunnerThreatState": "world_sim.baserunning",
	"SlideStepResult": "world_sim.baserunning",
	"StealOutcome": "world_sim.baserunning",
	"PickoffOutcome": "world_sim.baserunning",
	"prepare_runner_state": "world_sim.baserunning",
	"evaluate_slide_step": "world_sim.baserunning",
	"resolve_steal_attempt": "world_sim.baserunning",
	"simulate_pickoff": "world_sim.baserunning",
	"note_runner_pressure": "world_sim.baserunning",
	"BattedBall": "world_sim.fielding_engine",
	"FielderSnapshot": "world_sim.fielding_engine",
	"FieldingPlayResult": "world_sim.fielding_engine",
	"simulate_batted_ball": "world_sim.fielding_engine",
	"build_defense_alignment": "world_sim.fielding_engine",
	"resolve_fielding_play": "world_sim.fielding_engine",
}


def __getattr__(name: str) -> Any:  # pragma: no cover - glue code
	module_name = _MODULE_ATTRS.get(name)
	if module_name is None:
		raise AttributeError(f"module 'world_sim' has no attribute '{name}'")
	module = import_module(module_name)
	value = getattr(module, name)
	globals()[name] = value
	return value