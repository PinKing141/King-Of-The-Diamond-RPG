"""Interactive reflex-based mini game used during high-leverage pitches."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

from game.rng import get_rng
from ui.ui_display import Colour, render_clutch_banner, render_minigame_ui

_rng = get_rng()


@dataclass
class PitchMinigameContext:
    """Describes the narrative framing for the reflex challenge."""

    inning: int = 9
    half: str = "Top"
    count: str = "3-2"
    runners_on: int = 2
    score_diff: int = 0
    label: str = "Elimination Pitch"


@dataclass
class PitchMinigameResult:
    """Outcome payload returned by the minigame."""

    quality: float
    deviation: float
    cursor_position: float
    difficulty: float
    feedback: str
    context: PitchMinigameContext
    target_window: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _cursor_position(elapsed: float, speed: float) -> float:
    """Simulate a back-and-forth slider cursor based on elapsed time."""

    period = max(0.4, 1.6 / speed)
    cycle = (elapsed % period) / period  # 0..1
    double_cycle = cycle * 2
    if double_cycle <= 1:
        return double_cycle  # left -> right
    return 2 - double_cycle  # right -> left


def _describe_quality(quality: float) -> str:
    if quality >= 0.9:
        return "Perfect paint!" 
    if quality >= 0.75:
        return "Filthy black dot." 
    if quality >= 0.5:
        return "Competitive strike." 
    if quality >= 0.25:
        return "Missed spot—danger zone." 
    return "Meatball served up."


def run_minigame(
    control_stat: int,
    fatigue_level: int,
    pitch_difficulty: float,
    *,
    context: Optional[PitchMinigameContext] = None,
    auto_resolve: bool = False,
) -> PitchMinigameResult:
    """Run the slider minigame and return a quality score between 0 and 1."""

    context = context or PitchMinigameContext()
    control = _clamp(control_stat or 0, 0, 100)
    fatigue = _clamp(fatigue_level or 0, 0, 120)
    difficulty = _clamp(pitch_difficulty or 0.0, 0.0, 1.0)

    target_window = _clamp(0.18 + (control - 50) / 650 - difficulty * 0.08, 0.05, 0.28)
    fatigue_penalty = fatigue / 160.0
    cursor_speed = 1.2 + (difficulty * 0.6) + (fatigue / 200.0)

    if not auto_resolve:
        print(f"\n{Colour.CYAN}⚡ Showtime Pitch Incoming ⚡{Colour.RESET}")
        render_clutch_banner(
            inning=context.inning,
            half=context.half,
            count=context.count,
            score_diff=context.score_diff,
            runners_on=context.runners_on,
            label=context.label,
        )
        print("  Tap Enter exactly when you feel the cursor is centered.")
        print("  Control widens the safe window; fatigue and difficulty shrink it.")
        render_minigame_ui(None, target_window, show_target=True)
        input("  Press Enter to start the motion...")
        start = time.perf_counter()
        input("  SNAP IT! (Press Enter) ")
        elapsed = time.perf_counter() - start
    else:
        elapsed = _rng.random() * 1.2

    position = _cursor_position(elapsed, cursor_speed)
    deviation = abs(0.5 - position)
    normalized = _clamp(1.0 - (deviation / max(target_window, 1e-4)), 0.0, 1.0)
    quality = _clamp((normalized * (1.0 - fatigue_penalty)) + ((control - 50) / 200.0), 0.0, 1.0)
    feedback = _describe_quality(quality)

    if not auto_resolve:
        result_color = Colour.GREEN if quality >= 0.7 else Colour.YELLOW if quality >= 0.4 else Colour.RED
        render_minigame_ui(position, target_window, show_target=True, quality=quality)
        print(f"  Result: {result_color}{feedback}{Colour.RESET}\n")

    return PitchMinigameResult(
        quality=round(quality, 3),
        deviation=round(deviation, 3),
        cursor_position=round(position, 3),
        difficulty=round(difficulty, 2),
        feedback=feedback,
        context=context,
        target_window=round(target_window, 3),
    )


def trigger_pitch_minigame(
    *,
    inning: int,
    half: str,
    count: str,
    runners_on: int,
    score_diff: int,
    label: str,
    control_stat: int,
    fatigue_level: int,
    difficulty: float,
    auto_resolve: bool = False,
) -> PitchMinigameResult:
    """High-level helper that builds context and launches the minigame."""

    context = PitchMinigameContext(
        inning=inning,
        half=half,
        count=count,
        runners_on=runners_on,
        score_diff=score_diff,
        label=label,
    )
    return run_minigame(
        control_stat,
        fatigue_level,
        difficulty,
        context=context,
        auto_resolve=auto_resolve,
    )


__all__ = [
    "PitchMinigameContext",
    "PitchMinigameResult",
    "run_minigame",
    "trigger_pitch_minigame",
]
