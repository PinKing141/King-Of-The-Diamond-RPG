"""Bulk import verifier for game and world_sim modules."""
from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from pathlib import Path
from typing import Iterable, List, Tuple

TARGET_PACKAGES = ("game", "world_sim")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _discover_modules(package_name: str) -> Iterable[str]:
    module = importlib.import_module(package_name)
    yield module.__name__
    package_path = getattr(module, "__path__", None)
    if not package_path:
        return
    for finder, name, _ in pkgutil.walk_packages(package_path, prefix=f"{package_name}."):
        yield name


def main() -> int:
    failures: List[Tuple[str, str]] = []
    for package_name in TARGET_PACKAGES:
        for module_name in sorted(set(_discover_modules(package_name))):
            try:
                importlib.import_module(module_name)
            except Exception:  # Collect the traceback for reporting
                failures.append((module_name, traceback.format_exc()))
    if failures:
        print("Import failures detected:")
        for module_name, tb in failures:
            print(f"\n=== {module_name} ===\n{tb}")
        return 1
    print("All target modules imported successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
