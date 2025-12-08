"""Lightweight UI shim package for tests and CLI entrypoints.

This module re-exports the terminal UI helpers from `world.ui` so legacy imports
like `ui.ui_display` keep working without extra path tweaks.
"""

from ui.core import MenuChoice, UI, ui  # noqa: F401
from world.ui.ui_display import *  # noqa: F401,F403
