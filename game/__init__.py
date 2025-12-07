"""Compatibility shims for legacy import paths.

This package historically exposed many modules at the top level (e.g.
``from game import talent_tree``). The refactor into subpackages broke those
imports, so we lazily re-export the most commonly used modules here to keep
older callers and tests working without touching their import lines.
"""

import importlib
from types import ModuleType
from typing import Dict


_LAZY_MODULES: Dict[str, str] = {
	"training_logic": "game.training_logic",
	"save_manager": "game.save_manager",
	"ai_player_logic": "game.ai_player_logic",
	"talent_tree": "game.systems.talent_tree",
	"pitch_types": "game.mechanics.pitch_types",
	"commentary_pools": "game.story.commentary_pools",
	"stadiums": "game.story.stadiums",
}

__all__ = list(_LAZY_MODULES.keys())


def __getattr__(name: str) -> ModuleType:
	target = _LAZY_MODULES.get(name)
	if target is None:
		raise AttributeError(f"module 'game' has no attribute '{name}'")
	module = importlib.import_module(target)
	globals()[name] = module  # Cache for future lookups
	return module


def __dir__():
	return sorted(list(globals().keys()) + list(_LAZY_MODULES.keys()))