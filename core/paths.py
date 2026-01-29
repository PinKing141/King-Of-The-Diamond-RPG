from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from appdirs import user_data_dir
except ImportError:  # lightweight fallback
    def user_data_dir(appname: str, appauthor: str = "") -> str:
        """Minimal appdirs replacement with Windows-local awareness."""
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        else:
            base = Path.home() / ".local" / "share"
        target = base / appauthor / appname if appauthor else base / appname
        return str(target)


_APP_NAME = "King_of_the_Diamond"
_APP_AUTHOR = "KingStudios"


@dataclass
class AppPaths:
    root: Path
    data_dir: Path
    saves_dir: Path
    cache_dir: Path


def get_app_paths() -> AppPaths:
    data_dir = Path(user_data_dir(_APP_NAME, _APP_AUTHOR))
    saves_dir = data_dir / "saves"
    cache_dir = data_dir / "cache"
    for p in (data_dir, saves_dir, cache_dir):
        os.makedirs(p, exist_ok=True)
    return AppPaths(root=Path(__file__).resolve().parents[1], data_dir=data_dir, saves_dir=saves_dir, cache_dir=cache_dir)


def data_path(*parts: str) -> Path:
    """Resolve a path inside the packaged `data` directory."""
    return get_app_paths().root.joinpath("data", *parts)


def save_path(*parts: str) -> Path:
    """Resolve a path within the user save directory (appdirs-backed)."""
    return get_app_paths().saves_dir.joinpath(*parts)


def active_db_path(filename: str = "koshien_active.db") -> Path:
    """Return the path to the active SQLite database file in the save directory."""
    return save_path(filename)


def load_text_resource(package: str, resource_name: str) -> Optional[str]:
    """Load a bundled text resource using importlib.resources; return None if missing."""
    try:
        with resources.files(package).joinpath(resource_name).open("r", encoding="utf-8") as handle:
            return handle.read()
    except (FileNotFoundError, OSError, UnicodeError) as exc:
        logger.debug("Resource %s/%s not found or unreadable: %s", package, resource_name, exc)
        return None


def load_json_resource(package: str, resource_name: str):
    import json
    text = load_text_resource(package, resource_name)
    if text is None:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.debug("Resource %s/%s JSON decode failed: %s", package, resource_name, exc)
        return None
