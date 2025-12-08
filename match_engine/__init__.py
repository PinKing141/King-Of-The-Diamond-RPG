# Lightweight facade to avoid eager heavy imports that create circular dependencies

__all__ = ["run_match", "resolve_match", "BatterLike", "PitcherLike"]

from .interfaces import BatterLike, PitcherLike


def run_match(*args, **kwargs):
	from .controller import run_match as _run_match

	return _run_match(*args, **kwargs)


def resolve_match(*args, **kwargs):
	from .controller import resolve_match as _resolve_match

	return _resolve_match(*args, **kwargs)