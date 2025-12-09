"""Weekly scheduler view helpers kept in the UI layer."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from core.io_interface import IOInterface
from game.systems.academic_system import required_score_for_school
from ui.ui_display import (
    Colour,
    clear_screen as ui_clear_screen,
    render_weekly_dashboard as ui_render_weekly_dashboard,
)

__all__ = [
    "Colour",
    "clear_screen",
    "render_weekly_dashboard",
    "colourize",
    "render_weekly_brief",
    "render_planning_ui",
]


def clear_screen():
    return ui_clear_screen()


def render_weekly_dashboard(summary):
    return ui_render_weekly_dashboard(summary)


def colourize(label: str, colour_name: str) -> str:
    colour_value = getattr(Colour, colour_name.upper(), Colour.RESET)
    return f"{colour_value}{label}{Colour.RESET}"


def render_weekly_brief(
    player,
    current_week: int,
    coach_order=None,
    *,
    coach_order_requirement: Optional[str] = None,
    coach_order_rewards: Tuple[int, int] | None = None,
    io: Optional[IOInterface] = None,
):
    """Present a concise weekly prep snapshot for the active player."""

    log = io.log if io else print
    clear_fn = io.clear if io else ui_clear_screen
    school = getattr(player, "school", None)
    coach = getattr(school, "coach", None) if school else None
    squad = _infer_squad_status(player)
    fatigue = getattr(player, "fatigue", 0) or 0
    morale = getattr(player, "morale", 60) or 60
    trust = getattr(player, "trust_baseline", 50) or 50
    ability_points = getattr(player, "ability_points", 0) or 0
    academic_score = (
        player.test_score if getattr(player, "test_score", None) is not None else getattr(player, "academic_skill", 0)
    )
    target_score = required_score_for_school(school)

    clear_fn()
    log(f"{Colour.HEADER}=== WEEK {current_week}: TRAINING PREP ==={Colour.RESET}")
    if school:
        log(f"School: {school.name} ({school.prefecture})")
        era_label, era_momentum = _era_profile(school)
        log(f"Era Status: {era_label.title()} (Momentum {era_momentum:+d})")
    if coach:
        squad_label = "First-String" if squad == "FIRST" else "Second-String"
        log(f"Coach: {coach.name} | Expectations: {squad_label}")
    log(f"Player: {getattr(player, 'name', 'You')} | Position: {getattr(player, 'position', '?')} | Year {getattr(player, 'year', '?')}")
    log(f"Fatigue: {fatigue}/100 | Morale: {morale}")
    log(f"Coach Trust Baseline: {trust} | Ability Points: {ability_points}")
    log(f"Academic Standing: {academic_score} (Need {target_score}+ to stay eligible)")
    if coach_order:
        req_text = coach_order_requirement or "See coach orders"
        trust_reward, ability_reward = coach_order_rewards or (0, 0)
        log(f"Coach's Orders: {coach_order.description}")
        log(f"  Needs: {req_text} | Reward: +{trust_reward} Trust, +{ability_reward} Ability")


def render_planning_ui(
    schedule_state: List[List[Optional[str]]],
    current_day_idx: int,
    current_slot_idx: int,
    current_fatigue: int,
    mandatory_schedule: Dict[Tuple[int, int], str],
    coach_order=None,
    order_progress: Optional[Dict[str, int]] = None,
    team_load_snapshot: Optional[Tuple[float, float]] = None,
    school=None,
    *,
    coach_order_requirement: Optional[str] = None,
    coach_order_rewards: Tuple[int, int] | None = None,
    io: Optional[IOInterface] = None,
):
    """Draw the weekly calendar grid with action metadata and cursor focus."""

    log = io.log if io else print
    clear_fn = io.clear if io else ui_clear_screen

    def _slot_token(action: Optional[str], is_cursor: bool, is_mandatory: bool) -> str:
        key = _action_meta_key(action)
        meta = _ACTION_METADATA_LOOKUP.get(key, _ACTION_METADATA_DEFAULT)
        short = meta["short"][:4]
        base = short if action else "...."
        token = f"[{base:^4}]" if is_cursor else f" {base:^4} "
        if action:
            token = colourize(token, meta["colour"])
        if is_mandatory:
            token = f"{Colour.BOLD}{token}{Colour.RESET}"
        return token

    clear_fn()
    log(f"{Colour.HEADER}=== WEEKLY PLANNING ==={Colour.RESET}")

    if team_load_snapshot:
        avg_fatigue, avg_stamina = team_load_snapshot
        rest_lock = avg_fatigue >= 65.0 and avg_stamina <= 55.0
        caution = avg_fatigue >= 60.0 or avg_stamina <= 58.0
        if rest_lock:
            badge = f"{Colour.FAIL}[REST]{Colour.RESET}"
            status = "Optional practice locked"
        elif caution:
            badge = f"{Colour.WARNING}[EDGE]{Colour.RESET}"
            status = "Near lock threshold"
        else:
            badge = f"{Colour.GREEN}[READY]{Colour.RESET}"
            status = "Team cleared for optional reps"
        log(f" Team Load {badge}  Fatigue {avg_fatigue:5.1f}% | Stamina {avg_stamina:5.1f}  — {status}")
        if not rest_lock:
            log(f"  Cushion: {max(0.0, 65.0 - avg_fatigue):4.1f} fatigue pts / {max(0.0, avg_stamina - 55.0):4.1f} stamina pts")
        else:
            log("  Coaches will cancel optional workouts until the roster recovers.")

    header = "      " + " ".join([f"{d[:3]:^6}" for d in _DAYS_OF_WEEK])
    log(header)
    for day_idx in range(7):
        row_tokens: List[str] = []
        for slot_idx in range(3):
            is_cursor = day_idx == current_day_idx and slot_idx == current_slot_idx
            mandatory_action = mandatory_schedule.get((day_idx, slot_idx))
            current_action = schedule_state[day_idx][slot_idx]
            token = _slot_token(current_action, is_cursor, mandatory_action is not None)
            row_tokens.append(token)
        log(f"{_DAYS_OF_WEEK[day_idx]:<6} {' '.join(row_tokens)}")

    f_col = Colour.GREEN
    if current_fatigue > 85:
        f_col = Colour.YELLOW
    if current_fatigue > 95:
        f_col = Colour.RED
    log(f"Projected Fatigue: {f_col}{current_fatigue}/100{Colour.RESET}")
    if current_fatigue > 100:
        log(f"{Colour.FAIL}!!! DANGER: INJURY RISK EXTREME !!!{Colour.RESET}", level="error")
    elif current_fatigue > 85:
        log(f"{Colour.WARNING}Warning: High injury risk.{Colour.RESET}", level="warning")

    focus_label = "Review" if current_day_idx >= 7 else f"{_DAYS_OF_WEEK[current_day_idx]} {_SLOTS[current_slot_idx]}"
    log(f"Planning Focus: {Colour.BOLD}{focus_label}{Colour.RESET}")

    if current_day_idx < 7:
        planned_action = schedule_state[current_day_idx][current_slot_idx]
        fallback_action = mandatory_schedule.get((current_day_idx, current_slot_idx))
        focus_action = planned_action or fallback_action
        if focus_action:
            meta = _ACTION_METADATA_LOOKUP.get(_action_meta_key(focus_action), _ACTION_METADATA_DEFAULT)
            desc = meta.get("desc") or "No description"
            log(f"Selected Slot Effect: {Colour.BOLD}{desc}{Colour.RESET}")
            if fallback_action and planned_action != fallback_action:
                log(f"{Colour.WARNING}Coach expects {fallback_action.replace('_', ' ').title()} here.{Colour.RESET}")
    if coach_order:
        req_text = coach_order_requirement or "Complete actions"
        trust_reward, ability_reward = coach_order_rewards or (0, 0)
        log(f"Coach's Orders: {Colour.BOLD}{coach_order.description}{Colour.RESET} ({req_text})")
        log(f" Reward: +{trust_reward} Trust / +{ability_reward} Ability Points")
        if order_progress:
            progress = order_progress.get("progress", 0)
            target = order_progress.get("target", 0)
            remaining = order_progress.get("remaining", max(0, target - progress))
            status_colour = Colour.GREEN if progress >= target and target else Colour.CYAN
            status_label = "Completed" if progress >= target and target else f"{remaining} to go"
            log(f" Progress: {status_colour}{progress}/{target}{Colour.RESET} ({status_label})")


def _action_meta_key(action: Optional[str]) -> Optional[str]:
    if not action:
        return None
    if action in _HEAVY_TRAINING_ACTIONS:
        return "train_heavy"
    if action in _LIGHT_TRAINING_ACTIONS:
        return "train_light"
    if action.startswith("train_"):
        return "train_heavy"
    return action


def _era_profile(school) -> Tuple[str, int]:
    if not school:
        return "STABLE", 0
    label = (getattr(school, "current_era", "STABLE") or "STABLE").upper()
    momentum = int(getattr(school, "era_momentum", 0) or 0)
    return label, momentum


def _infer_squad_status(player) -> str:
    if player is None:
        return "SECOND"
    declared = getattr(player, "squad_status", None)
    if declared:
        return "FIRST" if declared == "FIRST_STRING" else "SECOND"
    if getattr(player, "is_starter", False):
        return "FIRST"
    role = (getattr(player, "role", "") or "").upper()
    if role in {"ACE", "STARTER", "LINEUP", "CLEANUP"}:
        return "FIRST"
    jersey = getattr(player, "jersey_number", None)
    if jersey is not None and jersey <= 30:
        return "FIRST"
    return "SECOND"


# Local copies of constants used for display only (kept in sync with scheduler logic).
_DAYS_OF_WEEK = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_SLOTS = ("Morning", "Afternoon", "Evening")
_HEAVY_TRAINING_ACTIONS = {
    "train_power",
    "train_control",
    "train_contact",
    "train_speed",
    "train_stamina",
    "train_vision",
    "train_fielding",
    "train_pitching",
    "train_defense",
}
_LIGHT_TRAINING_ACTIONS = {"rest", "mind", "social", "study", "stretch"}
_ACTION_METADATA_DEFAULT = {"short": "????", "colour": "dim", "desc": ""}
_ACTION_METADATA_LOOKUP = {
    "train_heavy": {"short": "TR_H", "colour": "yellow", "desc": "Heavy training rep"},
    "train_light": {"short": "TR_L", "colour": "cyan", "desc": "Light recovery or mindset"},
    "team_practice": {"short": "TEAM", "colour": "green", "desc": "Team practice"},
    "practice_match": {"short": "PMAT", "colour": "red", "desc": "Intrasquad match"},
    "b_team_match": {"short": "BTEAM", "colour": "magenta", "desc": "B-team reps"},
    "study": {"short": "STDY", "colour": "blue", "desc": "Study session"},
    "social": {"short": "SOC", "colour": "cyan", "desc": "Team bonding"},
    "rest": {"short": "REST", "colour": "green", "desc": "Rest and recovery"},
    "mind": {"short": "MIND", "colour": "yellow", "desc": "Mental prep"},
}
