"""
Lightweight architecture guardrails.

Rules enforced:
- world_sim.data_access may only be imported by the shim itself or the cache/service surfaces.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
WHITELIST_DATA_ACCESS = {
    ROOT / "world_sim" / "data_access.py",
    ROOT / "world_sim" / "strength_cache.py",
    ROOT / "world_sim" / "services" / "sim_data.py",
}


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part.startswith(".") for part in path.parts):
            continue
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        yield path


def _find_data_access_violations() -> List[Tuple[Path, int, str]]:
    pattern = re.compile(r"(^|\s)(from\s+world_sim\s+import\s+data_access|import\s+world_sim\.data_access)")
    violations: List[Tuple[Path, int, str]] = []
    for path in _iter_python_files(ROOT):
        if path in WHITELIST_DATA_ACCESS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                violations.append((path.relative_to(ROOT), lineno, line.strip()))
    return violations


def main() -> int:
    violations = []
    violations.extend(
        ("world_sim.data_access import restricted",) + v for v in _find_data_access_violations()
    )

    if not violations:
        print("architecture_guard: OK")
        return 0

    for rule, path, lineno, line in violations:
        print(f"{rule}: {path}:{lineno}: {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
