"""Sample several generated pitch arsenals to confirm modern pitch names appear."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.populate_japan import generate_pitch_arsenal, roll_arm_slot


class _StubPitcher:
    control = 65
    movement = 60


def collect_unique_pitch_names(samples: int = 200) -> set[str]:
    names: set[str] = set()
    stub = _StubPitcher()
    for _ in range(samples):
        slot = roll_arm_slot("pitching")
        for pitch in generate_pitch_arsenal(stub, "pitching", slot):
            names.add(pitch.pitch_name)
    return names


if __name__ == "__main__":
    unique = collect_unique_pitch_names()
    modern = sorted(name for name in unique if "hybrid" in name.lower() or "gyro" in name.lower() or "split" in name.lower() or "vulcan" in name.lower() or "power" in name.lower() or "rising" in name.lower())
    print(f"Generated {len(unique)} unique pitch names across {len(unique)} samples.")
    print("Sample modern-era names:", modern[:15])
