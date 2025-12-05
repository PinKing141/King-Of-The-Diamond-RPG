"""Compatibility shim that forwards legacy helpers to resolve_match."""
from .match_sim import resolve_match


def sim_match(*args, **kwargs):  # pragma: no cover - transitional helper
	return resolve_match(*args, **kwargs)


def sim_match_fast(*args, **kwargs):  # pragma: no cover - transitional helper
	kwargs.setdefault("mode", "fast")
	return resolve_match(*args, **kwargs)


__all__ = ["sim_match", "sim_match_fast"]