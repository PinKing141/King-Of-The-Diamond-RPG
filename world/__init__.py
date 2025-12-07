"""Lightweight world package init.

Avoid importing heavy generation modules (e.g., pykakasi dictionaries) at
package import time to keep test collection lean. Callers can still reach the
original helpers via the lazy wrappers below.
"""

from .school_philosophy import get_philosophy, PHILOSOPHY_MATRIX


def generate_coach_for_school(*args, **kwargs):
	"""Lazy-import coach generation to defer heavy dependencies."""
	from .coach_generation import generate_coach_for_school as _impl

	return _impl(*args, **kwargs)


def get_ledger(*args, **kwargs):
	from .rivals import get_ledger as _impl

	return _impl(*args, **kwargs)


def Rival(*args, **kwargs):
	from .rivals import Rival as _Impl

	return _Impl(*args, **kwargs)


def RivalMatchContext(*args, **kwargs):
	from .rivals import RivalMatchContext as _Impl

	return _Impl(*args, **kwargs)


__all__ = [
	"get_philosophy",
	"PHILOSOPHY_MATRIX",
	"generate_coach_for_school",
	"get_ledger",
	"Rival",
	"RivalMatchContext",
]