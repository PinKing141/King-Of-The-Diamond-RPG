"""Inspect pitch names stored in the active database and highlight modern additions."""
from collections import Counter

from database.setup_db import PitchRepertoire, session_scope

MODERN_KEYWORDS = [
    "gyro",
    "power",
    "split",
    "vulcan",
    "rising",
    "turbo",
    "hybrid",
    "vulcan",
]


def main():
    with session_scope() as session:
        rows = session.query(PitchRepertoire.pitch_name).all()

    names = [name for (name,) in rows]
    unique = sorted(set(names))

    modern = [n for n in unique if any(keyword in n.lower() for keyword in MODERN_KEYWORDS)]
    counts = Counter(names)

    print(f"Pitch entries: {len(names):,}")
    print(f"Unique pitch names: {len(unique)}")
    print(f"Modern-themed names detected: {len(modern)}")
    print("Sample modern names (up to 20):")
    for name in modern[:20]:
        print(f"  - {name} ({counts[name]} entries)")


if __name__ == "__main__":
    main()
