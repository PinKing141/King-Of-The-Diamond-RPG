"""Quick harness to probe wall/wild/pass-ball outcomes.

Not part of shipping gameplay; useful for sanity checks.
"""
from __future__ import annotations

import random
from types import SimpleNamespace

from match_engine.pitch_logic import PitchResult, _maybe_flag_wild_pitch


class DummyPlayer(SimpleNamespace):
    pass


def _make_state(catcher: DummyPlayer):
    lineup = [catcher]
    # Runners on first; runners list length 3.
    return SimpleNamespace(
        top_bottom="Top",
        home_lineup=lineup,
        away_lineup=[],
        runners=[object(), None, None],
        pitch_counts={1: 90},
        weather=None,
    )


def run_sim(label: str, control: int, wall: int, trials: int = 200) -> None:
    catcher = DummyPlayer(position="Catcher", catcher_ability=wall, fielding=wall, discipline=wall)
    pitcher = DummyPlayer(id=1, control=control)
    state = _make_state(catcher)

    counts = {"wild_pitch": 0, "passed_ball": 0, "blocked_pitch": 0, "clean": 0}
    for _ in range(trials):
        res = PitchResult("Test", "Zone", "Ball", "Ball", velocity=142)
        res.pitch_plane = "sink"
        _maybe_flag_wild_pitch(res, state, pitcher)
        tag = getattr(res, "special", None) or "clean"
        counts[tag] = counts.get(tag, 0) + 1
    print(f"{label} (control {control}, wall {wall}): {counts}")


if __name__ == "__main__":
    random.seed(7)
    run_sim("Good wall", control=42, wall=82)
    run_sim("Weak wall", control=42, wall=40)
