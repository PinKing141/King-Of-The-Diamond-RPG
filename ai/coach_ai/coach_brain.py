from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple

from database.setup_db import Coach


@dataclass(frozen=True)
class CoachArchetypeProfile:
    code: str
    stat_focus: Dict[str, float] = field(default_factory=dict)
    prefer_hot_form: bool = False
    prefer_youth: bool = False
    prefer_veterans: bool = False
    rest_bias: int = 0
    match_directives: Tuple[str, ...] = ()


def _profile(code: str, **kwargs) -> CoachArchetypeProfile:
    return CoachArchetypeProfile(code=code, **kwargs)


ARCHETYPE_PROFILES: Dict[str, CoachArchetypeProfile] = {
    "TRADITIONALIST": _profile(
        "TRADITIONALIST",
        stat_focus={"seniority": 0.25, "trust": 0.15},
        rest_bias=0,
    ),
    "BALANCED": _profile(
        "BALANCED",
        stat_focus={"stats": 0.1, "form": 0.1},
        rest_bias=2,
    ),
    "MOTIVATOR": _profile(
        "MOTIVATOR",
        stat_focus={"morale": 0.35, "trust": 0.2},
        prefer_hot_form=True,
        rest_bias=-6,
    ),
    "INNOVATOR": _profile(
        "INNOVATOR",
        stat_focus={"stats": 0.15, "potential": 0.25},
        prefer_youth=True,
        rest_bias=4,
    ),
    "SCIENTIST": _profile(
        "SCIENTIST",
        stat_focus={"stats": 0.2, "discipline": 0.15},
        prefer_hot_form=True,
        rest_bias=0,
    ),
    "TALENT_ENGINEER": _profile(
        "TALENT_ENGINEER",
        stat_focus={"potential": 0.4, "youth": 0.25},
        prefer_youth=True,
        rest_bias=3,
    ),
    "SLUGGER_GURU": _profile(
        "SLUGGER_GURU",
        stat_focus={"power": 0.6, "contact": 0.3},
        prefer_hot_form=True,
        rest_bias=5,
        match_directives=("power_focus",),
    ),
    "TACTICIAN": _profile(
        "TACTICIAN",
        stat_focus={"speed": 0.35, "fielding": 0.3, "discipline": 0.25},
        rest_bias=-4,
        match_directives=("small_ball",),
    ),
    "MENTOR": _profile(
        "MENTOR",
        stat_focus={"morale": 0.2, "seniority": 0.2},
        prefer_veterans=True,
        rest_bias=-2,
    ),
}

DEFAULT_PROFILE = ARCHETYPE_PROFILES["TRADITIONALIST"]

POTENTIAL_VALUES = {
    "S": 96,
    "A": 88,
    "B": 80,
    "C": 72,
    "D": 64,
    "E": 56,
    "F": 48,
}

YEAR_SCORES = {1: 30, 2: 60, 3: 85}


class CoachBrain:
    """Encapsulates archetype-driven decision making for a coach."""

    def __init__(self, coach: Coach):
        self.coach = coach
        archetype = (coach.archetype or "TRADITIONALIST").upper()
        self.profile = ARCHETYPE_PROFILES.get(archetype, DEFAULT_PROFILE)
        ability = getattr(coach, "scouting_ability", 50) or 50
        self._scouting_factor = max(0.0, (ability - 50) / 50.0)

    # --- utility tuning -------------------------------------------------
    def adjust_player_utility(
        self,
        player,
        base_value: float,
        *,
        stats_score: float,
        form_score: float,
        team_avg_overall: float,
    ) -> float:
        bonus = 0.0
        for trait, weight in self.profile.stat_focus.items():
            value = self._value_for_focus(player, trait, stats_score, form_score, team_avg_overall)
            bonus += (value - 50) * weight

        if self.profile.prefer_hot_form:
            bonus += (form_score - 50) * 0.35
        if self.profile.prefer_youth:
            bonus += max(0, 3 - (getattr(player, "year", 3) or 3)) * 4.0
        if self.profile.prefer_veterans:
            bonus += max(0, (getattr(player, "year", 1) or 1) - 1) * 4.5

        bonus += self._projection_bonus(player)
        return base_value + bonus

    def _value_for_focus(self, player, trait: str, stats_score: float, form_score: float, team_avg: float) -> float:
        if trait == "stats":
            return stats_score
        if trait == "form":
            return form_score
        if trait == "trust":
            return getattr(player, "trust_baseline", 50) or 50
        if trait == "morale":
            return getattr(player, "morale", 55) or 55
        if trait == "discipline":
            return getattr(player, "discipline", 55) or 55
        if trait == "speed":
            return getattr(player, "speed", 55) or 55
        if trait == "fielding":
            return getattr(player, "fielding", 55) or 55
        if trait == "power":
            return getattr(player, "power", 55) or 55
        if trait == "contact":
            return getattr(player, "contact", 55) or 55
        if trait == "velocity":
            return getattr(player, "velocity", 55) or 55
        if trait == "control":
            return getattr(player, "control", 55) or 55
        if trait == "stamina":
            return getattr(player, "stamina", 55) or 55
        if trait == "potential":
            return self._potential_value(player)
        if trait == "youth":
            return 80 if getattr(player, "year", 3) == 1 else 50
        if trait == "seniority":
            return YEAR_SCORES.get(getattr(player, "year", 3), 70)
        if trait == "team_leader":
            margin = stats_score - team_avg
            morale = getattr(player, "morale", 60) or 60
            return 60 + max(0, margin) * 0.6 + (morale - 50) * 0.4
        return 50.0

    def _potential_value(self, player) -> float:
        grade = (getattr(player, "potential_grade", "C") or "C").strip().upper()
        return POTENTIAL_VALUES.get(grade, 70)

    def _projection_bonus(self, player) -> float:
        if self._scouting_factor <= 0:
            return 0.0
        upside = self._potential_value(player) - 70
        is_underclass = (getattr(player, "year", 3) or 3) == 1
        tag = (getattr(player, "growth_tag", "normal") or "normal").lower()
        tag_bonus = 10 if tag in {"limitless", "supernova"} else 0
        bias = upside + tag_bonus
        if is_underclass:
            bias += 5
        return bias * 0.3 * self._scouting_factor

    # --- rest logic -----------------------------------------------------
    def should_rest_player(self, player) -> bool:
        fatigue = getattr(player, "fatigue", 0) or 0
        threshold = 78 + self.profile.rest_bias
        if getattr(player, "position", "") == "Pitcher":
            threshold -= 5
        if getattr(player, "year", 3) == 1 and self.profile.prefer_youth:
            threshold -= 5
        return fatigue >= threshold

    # --- strategy directives -------------------------------------------
    def ensure_strategy_mods(self, session, school_id: int) -> None:
        if not self.profile.match_directives:
            return
        from game.coach_strategy import has_modifier, set_strategy_modifier

        for effect in self.profile.match_directives:
            if has_modifier(session, school_id, effect):
                continue
            set_strategy_modifier(session, school_id, effect, games=5)

    # --- helpers --------------------------------------------------------
    @staticmethod
    def active_directives_for(coach: Coach) -> Iterable[str]:
        archetype = (coach.archetype or "TRADITIONALIST").upper()
        profile = ARCHETYPE_PROFILES.get(archetype, DEFAULT_PROFILE)
        return profile.match_directives
