"""Centralised loader for gameplay balancing data."""
from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional


class ConfigLoader:
    """Lazy JSON loader that exposes balancing data to the rest of the game."""

    _cache: Dict[str, Any] = {}
    _loaded: bool = False
    _lock: RLock = RLock()
    _path: Optional[Path] = None

    @classmethod
    def _default_path(cls) -> Path:
        env_path = os.getenv("BALANCING_CONFIG_PATH")
        if env_path:
            return Path(env_path).expanduser().resolve()
        base = Path(__file__).resolve().parents[1]
        return base / "data" / "balancing.json"

    @classmethod
    def configure(cls, *, path: Optional[str] = None) -> None:
        """Override the config path (useful for tests)."""
        cls._path = Path(path).expanduser().resolve() if path else None
        cls._loaded = False
        cls._cache = {}

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._loaded:
            return
        with cls._lock:
            if cls._loaded:
                return
            path = cls._path or cls._default_path()
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    cls._cache = json.load(handle)
            except FileNotFoundError:
                cls._cache = {}
            cls._loaded = True

    @classmethod
    def get_section(cls, section: str, default: Optional[Any] = None) -> Any:
        cls._ensure_loaded()
        if section not in cls._cache:
            return default
        value = cls._cache[section]
        if isinstance(value, dict):
            return value.copy()
        if isinstance(value, list):
            return list(value)
        return value

    @classmethod
    def get(cls, section: str, key: Optional[str] = None, default: Optional[Any] = None) -> Any:
        data = cls.get_section(section, default=None)
        if data is None:
            return default
        if key is None:
            return data
        if isinstance(data, dict):
            return data.get(key, default)
        raise TypeError(f"Section '{section}' is not a mapping; cannot access key '{key}'.")


__all__ = ["ConfigLoader"]
