from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Tuple, Dict

from database.setup_db import Player, School

# Regional and philosophy modifiers influence initial rolls
ACADEMIC_PREF_BONUS = {
    "Tokyo": 10,
    "Kanagawa": 8,
    "Kyoto": 7,
    "Osaka": 6,
    "Hyogo": 5,
    "Chiba": 4,
}

ACADEMIC_PREF_PENALTY = {
    "Okinawa": -6,
    "Kagoshima": -5,
    "Hokkaido": -3,
    "Aomori": -3,
}

PHILOSOPHY_ACADEMIC_BONUS = {
    "Academic Elite": 12,
    "Rich Private School": 6,
    "Scientific": 4,
    "Delinquent Squad": -12,
    "Modern Freedom": -4,
    "Average Joes": -2,
}

DEFAULT_PASSING_SCORE = 45

PHILOSOPHY_PASS_REQUIREMENTS = {
    "Academic Elite": 55,
    "Rich Private School": 52,
    "Scientific": 50,
    "Modern Freedom": 42,
    "Average Joes": 42,
    "Delinquent Squad": 40,
}

TEST_SCHEDULE: Dict[int, Dict[str, float]] = {
    6: {"name": "Golden Week Midterms", "difficulty": 0.95},
    14: {"name": "Summer Finals", "difficulty": 1.05},
    30: {"name": "Winter Exams", "difficulty": 1.10},
    44: {"name": "Graduation Comprehensive", "difficulty": 1.15},
}

GRADE_COMMENTS = [
    (90, "S", "Top percentile — teachers brag about you."),
    (80, "A", "Excellent work keeps the pride high."),
    (70, "B", "Solid pass. Coaches stay calm."),
    (60, "C", "Passing, but books should stay open."),
    (45, "D", "Warning level. Just above probation."),
    (0, "F", "Academic probation looming!"),
]


@dataclass
class StudyOutcome:
    summary: str
    fatigue_cost: int
    academic_gain: float
    test_gain: float


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def extract_prefecture_label(hometown: Optional[str]) -> str:
    if not hometown:
        return "Tokyo"
    for delimiter in ("—", "-", "|"):
        if delimiter in hometown:
            pref = hometown.split(delimiter, 1)[0].strip()
            return pref or "Tokyo"
    return hometown.strip() or "Tokyo"


def roll_academic_profile(hometown: Optional[str], school: Optional[School]) -> Tuple[int, int]:
    pref = extract_prefecture_label(hometown)
    base = random.randint(48, 72)
    base += ACADEMIC_PREF_BONUS.get(pref, 0)
    base += ACADEMIC_PREF_PENALTY.get(pref, 0)

    if school and getattr(school, "philosophy", None):
        base += PHILOSOPHY_ACADEMIC_BONUS.get(school.philosophy, 0)

    academic_skill = clamp(base + random.randint(-3, 4), 35, 95)
    latest_score = clamp(academic_skill + random.randint(-8, 6), 20, 100)
    return int(academic_skill), int(latest_score)


def _focus_descriptor(focus_scalar: float) -> str:
    if focus_scalar >= 0.95:
        return "Laser-focused study marathon."
    if focus_scalar >= 0.75:
        return "Productive block of studying."
    if focus_scalar >= 0.55:
        return "Managed to review the basics."
    return "Mental fog slowed you down."


def resolve_study_session(player: Player, fatigue: int) -> StudyOutcome:
    fatigue = fatigue or 0
    fatigue_penalty = max(0, fatigue - 35)
    focus_scalar = max(0.35, 1 - (fatigue_penalty / 140))

    base_gain = 0.65
    style_bonus = 0.1 if (player.growth_tag or "").lower() in {"grinder", "technical"} else 0.0
    academic_gain = (base_gain + style_bonus) * focus_scalar * random.uniform(0.85, 1.25)

    # Diminishing returns near mastery
    if (player.academic_skill or 0) >= 88:
        academic_gain *= 0.6
    if (player.academic_skill or 0) >= 95:
        academic_gain *= 0.4

    retention = 1.05 + (player.academic_skill or 50) / 140
    test_gain = academic_gain * retention

    # Fatigue cost grows once you're exhausted
    fatigue_cost = 4 + int(fatigue_penalty / 25)
    summary = f"Study Session: {_focus_descriptor(focus_scalar)}"
    return StudyOutcome(summary=summary, fatigue_cost=fatigue_cost, academic_gain=academic_gain, test_gain=test_gain)


def _grade_for_score(score: float):
    for threshold, grade, comment in GRADE_COMMENTS:
        if score >= threshold:
            return grade, comment
    return "F", "Academic probation looming!"


def maybe_run_academic_exam(player: Player, current_week: int) -> Optional[Dict[str, str]]:
    exam = TEST_SCHEDULE.get(current_week)
    if not exam:
        return None

    base_skill = player.academic_skill or 55
    previous_score = player.test_score if player.test_score is not None else base_skill
    fatigue = player.fatigue or 0
    fatigue_penalty = max(0, fatigue - 35) * 0.45

    difficulty = exam.get("difficulty", 1.0)
    difficulty_scalar = 1.05 - 0.15 * (difficulty - 1.0)
    difficulty_scalar = clamp(difficulty_scalar, 0.75, 1.15)

    knowledge_component = base_skill * 0.7
    momentum_component = previous_score * 0.3
    rng = random.gauss(0, 6)

    raw_score = (knowledge_component + momentum_component) * difficulty_scalar
    raw_score += rng
    raw_score -= fatigue_penalty

    score = clamp(raw_score, 0, 100)
    player.test_score = score

    # Move underlying skill slightly toward the new demonstrated level
    delta = (score - base_skill) * 0.08
    player.academic_skill = clamp(base_skill + delta, 25, 110)

    grade, comment = _grade_for_score(score)
    return {
        "exam_name": exam["name"],
        "score": str(int(round(score))),
        "grade": grade,
        "comment": comment,
    }


def required_score_for_school(school: Optional[School]) -> int:
    if school and getattr(school, "philosophy", None):
        return PHILOSOPHY_PASS_REQUIREMENTS.get(school.philosophy, DEFAULT_PASSING_SCORE)
    return DEFAULT_PASSING_SCORE


def is_academically_eligible(player: Player, school: Optional[School] = None) -> bool:
    current = player.test_score if player.test_score is not None else player.academic_skill or 0
    school = school or player.school
    return current >= required_score_for_school(school)


__all__ = [
    "roll_academic_profile",
    "resolve_study_session",
    "maybe_run_academic_exam",
    "is_academically_eligible",
    "required_score_for_school",
    "DEFAULT_PASSING_SCORE",
    "clamp",
]
