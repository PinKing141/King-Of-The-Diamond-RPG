import json
import time
import sys
import random
from sqlalchemy.exc import SQLAlchemyError
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from core.io_interface import IOInterface
from core.config_loader import ConfigLoader
from core.decisions import DecisionRequest

from database.setup_db import Player, GameState
from debug.debug_tools import input_with_debug
from sqlalchemy.orm import object_session
from core.constants import (
    ACTION_COSTS,
    ACTION_METADATA,
    ACTION_METADATA_DEFAULT,
    FIRST_STRING_WEEKEND,
    HEAVY_TRAINING_ACTIONS,
    LIGHT_TRAINING_ACTIONS,
    MANDATORY_TEAM_POLICY,
    BENCH_WEEKEND,
    SECOND_STRING_WEEKEND,
    SQUAD_FIRST_STRING,
    SQUAD_SECOND_STRING,
)
from world.roster_manager import run_roster_logic
# Import the bridge function from the new match engine location
from ui.ui_display import Colour, clear_screen, render_weekly_dashboard
from ui.console_view import ConsoleIO
# Import the new Event Manager
from game.story.event_manager import EventResult, trigger_random_event
from core.game_context import GameContext
from game.personnel.relationship_manager import seed_relationships
from game.systems.academic_system import (
    maybe_run_academic_exam,
    is_academically_eligible,
    required_score_for_school,
)
from game.mechanics.pitch_mastery import apply_mastery_decay, open_pitch_lab
from game.story.dialogue_manager import run_dialogue_event
from core.exceptions import ScheduleError
from game.loop.weekly_scheduler_core import (
    DAYS_OF_WEEK,
    SLOTS,
    WeekSummary,
    execute_schedule_core,
)
from core.sqlalchemy_repositories import SQLAlchemyPlayerRepository, SQLAlchemyTeamRepository
from game.services.progression_port import SQLAlchemyProgressionService
from game.systems.academic_system import score_to_letter_grade
from world.media_engine import generate_weekly_news


@dataclass(frozen=True)
class CoachOrder:
    key: str
    description: str
    requirement: Dict[str, object]
    reward_trust: int
    reward_ability_points: int


COACH_ORDER_DEFS: Tuple[CoachOrder, ...] = (
    CoachOrder(
        key="run_50km",
        description="Run 50km this week (plan 3 Speed drills).",
        requirement={"type": "action_count", "actions": ["train_speed"], "count": 3},
        reward_trust=4,
        reward_ability_points=1,
    ),
    CoachOrder(
        key="practice_pickoffs",
        description="Practice pick-offs twice this week.",
        requirement={
            "type": "action_count",
            "actions": ["train_control", "team_practice"],
            "count": 2,
        },
        reward_trust=3,
        reward_ability_points=1,
    ),
    CoachOrder(
        key="bullpen_command",
        description="Coach wants two high-intensity team reps.",
        requirement={
            "type": "action_count",
            "actions": ["team_practice", "practice_match"],
            "count": 2,
        },
        reward_trust=5,
        reward_ability_points=2,
    ),
)

AUTO_SCHEDULE_TEMPLATE: Tuple[Tuple[str, str, str], ...] = (
    ("train_power", "team_practice", "rest"),
    ("train_speed", "study", "social"),
    ("practice_match", "rest", "mind"),
    ("train_control", "team_practice", "rest"),
    ("train_contact", "study", "mind"),
    ("team_practice", "rest", "social"),
    ("rest", "mind", "social"),
)

SMART_SIM_FATIGUE_CAP = 92
_scheduler_cfg = ConfigLoader.get("weekly_scheduler", default={}) or {}
SMART_SIM_FATIGUE_CAP = int(_scheduler_cfg.get("smart_sim_fatigue_cap", SMART_SIM_FATIGUE_CAP))

ERA_PRESSURE_WEIGHTS = {
    "DYNASTY": 1.35,
    "ASCENDING": 1.15,
    "STABLE": 1.0,
    "RETOOLING": 0.9,
    "REBUILDING": 0.75,
}

ERA_REWARD_WEIGHTS = {
    "DYNASTY": 1.15,
    "ASCENDING": 1.05,
    "STABLE": 1.0,
    "RETOOLING": 0.95,
    "REBUILDING": 0.9,
}


def _era_profile(school) -> Tuple[str, int]:
    if not school:
        return "STABLE", 0
    label = (getattr(school, 'current_era', 'STABLE') or 'STABLE').upper()
    momentum = int(getattr(school, 'era_momentum', 0) or 0)
    return label, momentum


def _era_pressure_multiplier(school) -> float:
    label, momentum = _era_profile(school)
    base = ERA_PRESSURE_WEIGHTS.get(label, 1.0)
    return max(0.6, min(1.5, base + momentum * 0.01))


def _era_reward_multiplier(school) -> float:
    label, momentum = _era_profile(school)
    base = ERA_REWARD_WEIGHTS.get(label, 1.0)
    return max(0.7, min(1.4, base + momentum * 0.005))


def _effective_order_rewards(coach_order: Optional[CoachOrder], school) -> tuple[int, int]:
    if not coach_order:
        return 0, 0
    trust_mult = _era_reward_multiplier(school)
    trust_reward = max(1, int(round(coach_order.reward_trust * trust_mult))) if coach_order.reward_trust else 0
    return trust_reward, coach_order.reward_ability_points


def _summarize_execution(current_week: int, execution) -> WeekSummary:
    summary = WeekSummary(week_number=current_week)
    for warning in execution.warnings:
        summary.add_warning(warning)
    for slot in execution.results:
        summary.record_slot(slot)
    if getattr(execution, "headlines", None):
        summary.newsletter = list(execution.headlines)
    return summary

# --- CONSTANT HELPERS ---

def _action_meta_key(action: Optional[str]) -> Optional[str]:
    if not action:
        return None
    if action in HEAVY_TRAINING_ACTIONS:
        return 'train_heavy'
    if action in LIGHT_TRAINING_ACTIONS:
        return 'train_light'
    if action.startswith('train_'):
        return 'train_heavy'
    return action


def _colourize(label: str, colour_name: str) -> str:
    colour_value = getattr(Colour, colour_name.upper(), Colour.RESET)
    return f"{colour_value}{label}{Colour.RESET}"


def _infer_squad_status(player: Optional[Player]) -> str:
    if player is None:
        return SQUAD_SECOND_STRING
    declared = getattr(player, "squad_status", None)
    if declared in {SQUAD_FIRST_STRING, SQUAD_SECOND_STRING}:
        return declared
    if getattr(player, "is_starter", False):
        return SQUAD_FIRST_STRING
    role = (getattr(player, "role", "") or "").upper()
    if role in {"ACE", "STARTER", "LINEUP", "CLEANUP"}:
        return SQUAD_FIRST_STRING
    return SQUAD_SECOND_STRING


def _is_reserve_player(player: Optional[Player]) -> bool:
    if not player:
        return False
    role = (getattr(player, "role", "") or "").upper()
    jersey = getattr(player, "jersey_number", None)
    if role == "RESERVE":
        return True
    # Heuristic: deep reserves get late numbers (90+ or 99)
    return jersey is not None and jersey >= 90


def _is_bench_player(player: Optional[Player]) -> bool:
    if not player:
        return False
    role = (getattr(player, "role", "") or "").upper()
    jersey = getattr(player, "jersey_number", None)
    if role == "BENCH":
        return True
    # Heuristic: bench is in the teens; exclude starters (1-9) and reserves (90+)
    return jersey is not None and 10 <= jersey <= 89


def build_mandatory_schedule(player: Optional[Player]) -> Dict[Tuple[int, int], str]:
    if not player:
        return {}

    try:
        base = dict(MANDATORY_TEAM_POLICY)
        squad = _infer_squad_status(player)
        if squad == SQUAD_FIRST_STRING:
            weekend = FIRST_STRING_WEEKEND
        else:
            weekend = SECOND_STRING_WEEKEND if _is_reserve_player(player) else BENCH_WEEKEND
        base.update(weekend)
        return base
    except Exception as exc:
        raise ScheduleError(f"Failed to build mandatory schedule for {getattr(player, 'name', 'player')}: {exc}") from exc


def _get_active_player(context: GameContext) -> Optional[Player]:
    if context.player_id is None:
        return None
    return context.session.get(Player, context.player_id)


def _select_coach_order(player: Optional[Player], current_week: int) -> Optional[CoachOrder]:
    if not player or not COACH_ORDER_DEFS:
        return None
    seed = (getattr(player, 'id', 0) or 0) * 97 + current_week * 31
    rng = random.Random(seed)
    return rng.choice(COACH_ORDER_DEFS)


def _schedule_seed(context: GameContext, current_week: int) -> int:
    """Deterministic per-week seed to drive TrainingService and practice RNG."""

    player_component = (context.player_id or 0) * 1_001
    school_component = (context.school_id or 0) * 37
    return player_component + school_component + current_week * 101


def _describe_order_requirement(order: CoachOrder) -> str:
    requirement = order.requirement or {}
    if requirement.get('type') == 'action_count':
        actions = requirement.get('actions') or []
        action_labels = ", ".join(action.replace('_', ' ').title() for action in actions)
        count = requirement.get('count', 0)
        return f"{count}x [{action_labels}]"
    return "Unknown"


def _evaluate_order_progress(order: Optional[CoachOrder], slot_results: List['SlotResult']) -> Optional[Dict[str, int]]:
    if not order:
        return None
    requirement = order.requirement or {}
    if requirement.get('type') == 'action_count':
        actions = set(requirement.get('actions') or [])
        progress = sum(1 for result in slot_results if result.action in actions)
        target = int(requirement.get('count', 0))
        return {
            "progress": progress,
            "target": target,
            "completed": int(progress >= target),
        }
    return {"progress": 0, "target": 0, "completed": 0}


def _calculate_schedule_order_progress(
    order: Optional[CoachOrder], schedule_state: List[List[Optional[str]]]
) -> Optional[Dict[str, int]]:
    if not order:
        return None
    requirement = order.requirement or {}
    if requirement.get('type') != 'action_count':
        return None
    actions = set(requirement.get('actions') or [])
    target = int(requirement.get('count', 0))
    progress = 0
    for day_slots in schedule_state:
        for entry in day_slots:
            if entry in actions:
                progress += 1
    return {
        "progress": progress,
        "target": target,
        "remaining": max(0, target - progress),
        "completed": int(progress >= target),
    }


def _team_load_snapshot(player: Optional[Player]) -> Optional[Tuple[float, float]]:
    if not player:
        return None
    school_id = getattr(player, "school_id", None)
    if not school_id:
        return None
    roster: Optional[List[Player]] = None
    session = object_session(player)
    if session is not None:
        try:
            roster = session.query(Player).filter(Player.school_id == school_id).all()
        except SQLAlchemyError as exc:
            # Log and continue with fallback lookup so we don't silently lose roster context.
            print(f"Roster lookup failed for school_id={school_id}: {exc}")
            roster = None
    if not roster:
        school = getattr(player, "school", None)
        roster = list(getattr(school, "players", []) or []) if school else None
    if not roster:
        return None
    total_fatigue = 0.0
    total_stamina = 0.0
    count = 0
    for member in roster:
        total_fatigue += float(getattr(member, "fatigue", 0) or 0)
        total_stamina += float(getattr(member, "stamina", 0) or 0)
        count += 1
    if count == 0:
        return None
    return (total_fatigue / count, total_stamina / count)


def _record_coach_order_result(
    session,
    *,
    current_week: int,
    player: Optional[Player],
    coach_order: Optional[CoachOrder],
    order_progress: Optional[Dict[str, int]],
    reward_delta: Optional[Dict[str, int]] = None,
) -> None:
    """Persist the latest Coach's Orders outcome onto GameState."""

    if session is None or coach_order is None or order_progress is None:
        return

    try:
        gamestate_row = session.query(GameState).first()
    except SQLAlchemyError as exc:
        print(f"Coach order result persistence skipped: {exc}")
        return

    if not gamestate_row:
        return

    progress_value = int(order_progress.get("progress", 0) or 0)
    target_value = int(order_progress.get("target", 0) or 0)
    completion_flag = bool(order_progress.get("completed")) if target_value else progress_value >= target_value
    reward_delta = reward_delta or {}

    payload = {
        "week": int(current_week or 0),
        "player": {
            "id": getattr(player, "id", None),
            "name": getattr(player, "name", None),
            "position": getattr(player, "position", None),
            "school_id": getattr(player, "school_id", None),
        },
        "order": {
            "key": coach_order.key,
            "description": coach_order.description,
            "requirement": coach_order.requirement,
            "reward_trust": coach_order.reward_trust,
            "reward_ability_points": coach_order.reward_ability_points,
        },
        "progress": {
            "value": progress_value,
            "target": target_value,
            "remaining": max(0, target_value - progress_value),
        },
        "completed": completion_flag,
        "reward_delta": {
            "trust": int(reward_delta.get("trust", 0) or 0),
            "ability_points": int(reward_delta.get("ability_points", 0) or 0),
        },
        "timestamp": int(time.time()),
    }

    gamestate_row.last_coach_order_result = json.dumps(payload)
    session.add(gamestate_row)

# --- TRUST + PRESENTATION HELPERS ---

MANDATORY_TRUST_PENALTIES = {
    "practice_match": 7,
    "team_practice": 5,
    "b_team_match": 4,
    "train_heavy": 3,
}
DEFAULT_TRUST_PENALTY = 3
MIN_TRUST_BASELINE = 20
MORALE_PENALTY_PER_SKIP = 2
MAX_MORALE_PENALTY = 10


def _format_action_label(action: Optional[str]) -> str:
    if not action:
        return "Unassigned"
    return action.replace('_', ' ').title()


def _print_weekly_brief(
    player: Player,
    current_week: int,
    coach_order: Optional[CoachOrder] = None,
    *,
    io: Optional[IOInterface] = None,
) -> None:
    log = io.log if io else print
    clear_fn = io.clear if io else clear_screen
    school = getattr(player, 'school', None)
    coach = getattr(school, 'coach', None) if school else None
    squad = _infer_squad_status(player)
    fatigue = player.fatigue or 0
    morale = player.morale or 60
    trust = player.trust_baseline or 50
    academic_score = player.test_score if player.test_score is not None else (player.academic_skill or 0)
    target_score = required_score_for_school(school)

    clear_fn()
    log(f"{Colour.HEADER}=== WEEK {current_week}: TRAINING PREP ==={Colour.RESET}")
    if school:
        log(f"School: {school.name} ({school.prefecture})")
        era_label, era_momentum = _era_profile(school)
        log(f"Era Status: {era_label.title()} (Momentum {era_momentum:+d})")
    if coach:
        log(f"Coach: {coach.name} | Expectations: {'First-String' if squad == SQUAD_FIRST_STRING else 'Second-String'}")
    log(f"Player: {player.name or 'You'} | Position: {player.position} | Year {player.year}")
    log(f"Fatigue: {fatigue}/100 | Morale: {morale}")
    ability_points = getattr(player, 'ability_points', 0) or 0
    log(f"Coach Trust Baseline: {trust} | Ability Points: {ability_points}")
    log(f"Academic Standing: {academic_score} (Need {target_score}+ to stay eligible)")
    if coach_order:
        req_text = _describe_order_requirement(coach_order)
        effective_trust, effective_ability = _effective_order_rewards(coach_order, school)
        log(
            f"Coach's Orders: {coach_order.description}"
        )
        log(
            f"  Needs: {req_text} | Reward: +{effective_trust} Trust, +{effective_ability} Ability"
        )


def _process_skipped_penalties(
    context: GameContext,
    player: Player,
    skipped: List[Dict[str, object]],
):
    if not skipped:
        context.clear_temp_effect('skipped_mandatory_slots')
        return None

    trust_penalty = 0
    for slot in skipped:
        expected = slot.get("expected")
        trust_penalty += MANDATORY_TRUST_PENALTIES.get(expected, DEFAULT_TRUST_PENALTY)

    pressure_multiplier = _era_pressure_multiplier(getattr(player, 'school', None))
    trust_penalty = max(1, int(round(trust_penalty * pressure_multiplier))) if trust_penalty else 0

    morale_penalty = min(MAX_MORALE_PENALTY, MORALE_PENALTY_PER_SKIP * len(skipped))
    old_trust = player.trust_baseline or 50
    new_trust = max(MIN_TRUST_BASELINE, old_trust - trust_penalty)
    player.trust_baseline = new_trust
    player.morale = max(0, (player.morale or 60) - morale_penalty)

    payload = {
        "entries": skipped,
        "trust_penalty": trust_penalty,
        "morale_penalty": morale_penalty,
        "old_trust": old_trust,
        "new_trust": new_trust,
    }
    context.set_temp_effect('skipped_mandatory_slots', payload)
    return payload


def _initialize_week(
    context: GameContext,
    current_week: int,
    *,
    enable_events: bool = True,
    io: Optional[IOInterface] = None,
):
    player = _get_active_player(context)
    if not player:
        return None, None, None, None

    for key in ('mentor_training', 'rival_pressure', 'skipped_mandatory_slots'):
        context.clear_temp_effect(key)

    session = context.session
    seed_relationships(session, player)

    if context.school_id:
        run_roster_logic(target_school_id=context.school_id, db_session=session)
        session.refresh(player)

    exam_summary = maybe_run_academic_exam(player, current_week)
    if exam_summary:
        session.add(player)
        session.commit()

    event_result: Optional[EventResult] = None
    if enable_events:
        event_result = trigger_random_event(context, current_week, io=io)

    player = _get_active_player(context)
    coach_order = _select_coach_order(player, current_week) if player else None
    return player, coach_order, exam_summary, event_result


def _finalize_week_outcomes(
    context: GameContext,
    *,
    current_week: int,
    coach_order: Optional[CoachOrder],
    execution,
    skipped_mandatory: List[Dict[str, object]],
    summary: WeekSummary,
    exam_summary: Optional[dict] = None,
    event_text: Optional[str] = None,
) -> WeekSummary:
    player = _get_active_player(context)
    session = context.session

    if exam_summary:
        exam_label = exam_summary.get('exam_name', 'Exam')
        exam_score = exam_summary.get('score')
        exam_grade = exam_summary.get('grade')
        summary.add_event(f"{exam_label}: {exam_score} ({exam_grade})")
        comment = exam_summary.get('comment')
        if comment:
            summary.add_event(comment)

    if event_text:
        summary.add_event(event_text)

    order_progress = _evaluate_order_progress(coach_order, execution.results if execution else [])
    reward_delta = {"trust": 0, "ability_points": 0}
    if coach_order and order_progress and player:
        completed = bool(order_progress.get("completed"))
        progress = order_progress.get("progress", 0)
        target = order_progress.get("target", 0)
        if completed:
            trust_gain, ability_gain = _effective_order_rewards(coach_order, getattr(player, 'school', None))
            old_trust = player.trust_baseline or 50
            player.trust_baseline = min(100, old_trust + trust_gain)
            player.ability_points = (player.ability_points or 0) + ability_gain
            session.add(player)
            reward_delta = {"trust": trust_gain, "ability_points": ability_gain}
            summary.add_event(
                f"Coach's Orders complete (+{trust_gain} Trust / +{ability_gain} Ability)."
            )
        else:
            summary.add_warning(
                f"Coach's Orders incomplete ({progress}/{target})."
            )

        _record_coach_order_result(
            session,
            current_week=current_week,
            player=player,
            coach_order=coach_order,
            order_progress=order_progress,
            reward_delta=reward_delta,
        )

    penalty_payload = _process_skipped_penalties(context, player, skipped_mandatory)
    if penalty_payload:
        session.add(player)
        session.commit()
        summary.add_warning(
            f"Coach trust -{penalty_payload['trust_penalty']} / Morale -{penalty_payload['morale_penalty']}"
        )
        summary.add_event("Coaches noted missed mandatory work.")
        for slot in penalty_payload['entries']:
            expected = _format_action_label(slot.get('expected'))
            chosen = _format_action_label(slot.get('chosen'))
            summary.add_warning(
                f"Skipped {slot['day']} {slot['slot']}: expected {expected} -> {chosen}"
            )
    else:
        session.commit()

    maintained = False
    if execution and getattr(execution, "results", None):
        maintained = any(
            any(token in (res.action or "").lower() for token in ("pitch", "bullpen"))
            for res in execution.results
        )
    if getattr(player, "position", "") in {"Pitcher", "Two-Way", "Two-way"}:
        decay_log: List[str] = []
        try:
            apply_mastery_decay(session, player, maintained=maintained, log=decay_log)
        except SQLAlchemyError as exc:
            decay_log = [f"Pitch mastery decay skipped: {exc}"]
        for entry in decay_log:
            summary.add_event(entry)

    school = getattr(player, "school", None)
    team_name = getattr(school, "name", "Team")
    try:
        summary.newsletter = generate_weekly_news(
            summary,
            team_name=team_name,
            week=current_week,
            headlines=summary.newsletter or getattr(execution, "headlines", None),
            prestige=getattr(school, "prestige", None),
        )
    except Exception as exc:
        # If media generation fails, surface the issue instead of failing silently.
        summary.add_warning(f"Weekly news generation failed: {exc}")

    context.set_temp_effect('last_week_summary', summary.to_payload())
    return summary


def _safe_action_choice(template_action: str, projected_fatigue: int) -> str:
    if projected_fatigue >= 95:
        return 'rest'
    if projected_fatigue >= 85 and template_action not in {'rest', 'mind', 'study'}:
        return 'rest'
    if projected_fatigue >= 75 and template_action.startswith('train_'):
        return 'mind'
    return template_action


def _inject_order_requirements(
    schedule_state: List[List[Optional[str]]],
    coach_order: Optional[CoachOrder],
) -> None:
    if not coach_order:
        return
    requirement = coach_order.requirement or {}
    if requirement.get('type') != 'action_count':
        return
    actions = list(requirement.get('actions') or [])
    target = int(requirement.get('count', 0))
    if not actions or target <= 0:
        return
    slots = [
        (day_idx, slot_idx)
        for day_idx in range(7)
        for slot_idx in range(3)
        if schedule_state[day_idx][slot_idx] is None
    ]
    random.shuffle(slots)
    placed = 0
    for day_idx, slot_idx in slots:
        schedule_state[day_idx][slot_idx] = random.choice(actions)
        placed += 1
        if placed >= target:
            break


def generate_auto_schedule(player: Optional[Player], coach_order: Optional[CoachOrder] = None):
    schedule_state = [[None for _ in range(3)] for _ in range(7)]
    mandatory_schedule = build_mandatory_schedule(player)
    for (day_idx, slot_idx), action in mandatory_schedule.items():
        schedule_state[day_idx][slot_idx] = action

    _inject_order_requirements(schedule_state, coach_order)

    projected_fatigue = (player.fatigue or 0) if player else 0
    for day_idx, template_row in enumerate(AUTO_SCHEDULE_TEMPLATE):
        for slot_idx, template_action in enumerate(template_row):
            if schedule_state[day_idx][slot_idx]:
                projected_fatigue = max(0, projected_fatigue + get_action_cost(schedule_state[day_idx][slot_idx]))
                continue
            chosen = _safe_action_choice(template_action, projected_fatigue)
            schedule_state[day_idx][slot_idx] = chosen
            projected_fatigue = max(0, projected_fatigue + get_action_cost(chosen))

    is_pitcher = player and (getattr(player, "position", "") or "").lower().startswith("pitch")
    if is_pitcher:
        planned_actions = [action for day in schedule_state for action in day if action]
        if "bullpen_session" not in planned_actions:
            replaceable: List[Tuple[int, int]] = []
            for d_idx in range(7):
                for s_idx in range(3):
                    if (d_idx, s_idx) in mandatory_schedule:
                        continue
                    planned = schedule_state[d_idx][s_idx]
                    if planned and (planned.startswith("train_") or planned in {"team_practice", "practice_match"}):
                        replaceable.append((d_idx, s_idx))
            target_slot = replaceable[0] if replaceable else None
            if target_slot:
                schedule_state[target_slot[0]][target_slot[1]] = "bullpen_session"

    return schedule_state, mandatory_schedule


def run_week_automatic(context: GameContext, current_week: int, *, rng_seed=None):
    player, coach_order, exam_summary, event_result = _initialize_week(context, current_week, enable_events=False, io=None)
    if not player:
        summary = WeekSummary(week_number=current_week)
        summary.flag_interrupt("Active player missing; cannot simulate week.")
        return None, summary

    schedule_grid, _ = generate_auto_schedule(player, coach_order)
    skipped_mandatory: List[Dict[str, object]] = []

    try:
        seed = rng_seed if rng_seed is not None else _schedule_seed(context, current_week)
        execution, summary = execute_schedule_silent(
            context,
            schedule_grid,
            current_week,
            rng_seed=seed,
        )
    except ValueError as err:
        summary = WeekSummary(week_number=current_week)
        summary.add_warning(str(err))
        summary.flag_interrupt("Schedule aborted")
        return None, summary

    summary.add_schedule_note("Auto-schedule executed by staff.")
    event_text = event_result.summary if event_result else None

    summary = _finalize_week_outcomes(
        context,
        current_week=current_week,
        coach_order=coach_order,
        execution=execution,
        skipped_mandatory=skipped_mandatory,
        summary=summary,
        exam_summary=exam_summary,
        event_text=None,
    )
    refreshed_player = _get_active_player(context)
    if refreshed_player and (refreshed_player.fatigue or 0) >= SMART_SIM_FATIGUE_CAP:
        summary.flag_interrupt(
            f"Fatigue reached {(refreshed_player.fatigue or 0)}%."
        )
    return execution, summary

# --- HELPER FUNCTIONS ---

def get_action_cost(action_key):
    if not action_key:
        return 0
    if action_key in HEAVY_TRAINING_ACTIONS:
        return ACTION_COSTS['train_heavy']
    if action_key in LIGHT_TRAINING_ACTIONS:
        return ACTION_COSTS['train_light']
    return ACTION_COSTS.get(action_key, 0)

def render_planning_ui(
    schedule_state,
    current_day_idx,
    current_slot_idx,
    current_fatigue,
    mandatory_schedule: Dict[Tuple[int, int], str],
    coach_order: Optional[CoachOrder] = None,
    order_progress: Optional[Dict[str, int]] = None,
    team_load_snapshot: Optional[Tuple[float, float]] = None,
    school=None,
    *,
    io: Optional[IOInterface] = None,
):
    """Draws the weekly calendar grid with action metadata + cursor focus."""

    log = io.log if io else print
    clear_fn = io.clear if io else clear_screen

    def _slot_token(action: Optional[str], is_cursor: bool, is_mandatory: bool) -> str:
        key = _action_meta_key(action)
        meta = ACTION_METADATA.get(key, ACTION_METADATA_DEFAULT)
        short = meta["short"][:4]
        base = short if action else "...."
        token = f"[{base:^4}]" if is_cursor else f" {base:^4} "
        if action:
            token = _colourize(token, meta["colour"])
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
        log(
            f" Team Load {badge}  Fatigue {avg_fatigue:5.1f}% | Stamina {avg_stamina:5.1f}  — {status}"
        )
        if not rest_lock:
            log(
                f"  Cushion: {max(0.0, 65.0 - avg_fatigue):4.1f} fatigue pts / {max(0.0, avg_stamina - 55.0):4.1f} stamina pts"
            )
        else:
            log("  Coaches will cancel optional workouts until the roster recovers.")

    header = "      " + " ".join([f"{d[:3]:^6}" for d in DAYS_OF_WEEK])
    log(header)

    for s_idx, slot_name in enumerate(SLOTS):
        row_str = f"{slot_name[0].upper()} | "
        for d_idx in range(7):
            action = schedule_state[d_idx][s_idx]
            is_cursor = (d_idx, s_idx) == (current_day_idx, current_slot_idx)
            is_mandatory = (d_idx, s_idx) in mandatory_schedule
            row_str += _slot_token(action, is_cursor, is_mandatory) + " "
        log(row_str)

    log("-" * 72)

    f_col = Colour.GREEN
    if current_fatigue > 50:
        f_col = Colour.YELLOW
    if current_fatigue > 90:
        f_col = Colour.RED

    log(f"Projected Fatigue: {f_col}{current_fatigue}/100{Colour.RESET}")
    if current_fatigue > 100:
        log(f"{Colour.FAIL}!!! DANGER: INJURY RISK EXTREME !!!{Colour.RESET}", level="error")
    elif current_fatigue > 85:
        log(f"{Colour.WARNING}Warning: High injury risk.{Colour.RESET}", level="warning")

    focus_label = "Review" if current_day_idx >= 7 else f"{DAYS_OF_WEEK[current_day_idx]} {SLOTS[current_slot_idx]}"
    log(f"Planning Focus: {Colour.BOLD}{focus_label}{Colour.RESET}")

    if current_day_idx < 7:
        planned_action = schedule_state[current_day_idx][current_slot_idx]
        fallback_action = mandatory_schedule.get((current_day_idx, current_slot_idx))
        focus_action = planned_action or fallback_action
        if focus_action:
            meta = ACTION_METADATA.get(_action_meta_key(focus_action), ACTION_METADATA_DEFAULT)
            desc = meta.get("desc") or "No description"
            log(f"Selected Slot Effect: {Colour.BOLD}{desc}{Colour.RESET}")
            if fallback_action and planned_action != fallback_action:
                log(
                    f"{Colour.WARNING}Coach expects {fallback_action.replace('_', ' ').title()} here.{Colour.RESET}"
                )
    if coach_order:
        req_text = _describe_order_requirement(coach_order)
        log(
            f"Coach's Orders: {Colour.BOLD}{coach_order.description}{Colour.RESET} ({req_text})"
        )
        effective_trust, effective_ability = _effective_order_rewards(coach_order, school)
        log(
            f" Reward: +{effective_trust} Trust / +{effective_ability} Ability Points"
        )
        if order_progress:
            progress = order_progress.get("progress", 0)
            target = order_progress.get("target", 0)
            remaining = order_progress.get("remaining", max(0, target - progress))
            status_colour = Colour.GREEN if progress >= target and target else Colour.CYAN
            status_label = "Completed" if progress >= target and target else f"{remaining} to go"
            log(
                f" Progress: {status_colour}{progress}/{target}{Colour.RESET} ({status_label})"
            )


    def _resolve_prompt(
        message: str,
        *,
        io: Optional[IOInterface] = None,
        context=None,
        session=None,
        state=None,
        options: Optional[List[str]] = None,
        default: str = "",
    ) -> Optional[str]:
        """Route prompt through DecisionRequest for UI layers that defer input."""

        request = DecisionRequest(
            kind="prompt",
            message=message,
            options=options,
            default=default,
            payload={"context": "weekly_scheduler"},
        )
        handler = getattr(io, "handle_decision_requests", None) if io else None
        if callable(handler):
            response = handler([request])
            if response is not None:
                return response

        prompt_fn = io.prompt if io else (lambda msg, **kwargs: input_with_debug(msg, context=context, session=session, state=state))
        return prompt_fn(message, options=options)

def get_slot_choice(current_action: Optional[str], *, context=None, session=None, state=None, io: Optional[IOInterface] = None) -> Optional[str]:
    """Prompts the user for an action selection, defaulting to the current value."""
    log = io.log if io else print

    log("\nSelect Action (Enter = keep current plan):")
    if current_action:
        log(f" Current: {current_action.replace('_', ' ').title()}")
    log(f" 1. {Colour.CYAN}TRAIN{Colour.RESET} (Drills)")
    log(f" 2. {Colour.GREEN}REST{Colour.RESET}  (Recover)")
    log(f" 3. {Colour.BLUE}LIFE{Colour.RESET}  (Study/Social)")
    log(" 0. BACK | X. EXIT PLANNING")

    choice_raw = _resolve_prompt(">> ", io=io, context=context, session=session, state=state)
    if choice_raw is None:
        return None
    choice = choice_raw.strip().lower()
    if choice == "":
        return current_action

    if choice in {"x", "exit"}:
        return "EXIT"

    if choice == '1':
        log("   [P]ower  [S]peed  [St]amina  [C]ontrol  [Co]ntact  [Bu]llpen  [B]ack")
        sub = (_resolve_prompt("   Drill: ", io=io, context=context, session=session, state=state) or "").lower().strip()
        mapping = {
            'p': 'train_power',
            's': 'train_speed',
            'st': 'train_stamina',
            'c': 'train_control',
            'co': 'train_contact',
            'bu': 'bullpen_session',
        }
        return mapping.get(sub)

    if choice == '2':
        return 'rest'

    if choice == '3':
        log("   [S]tudy  [F]riends  [M]ind  [B]ack")
        sub = (_resolve_prompt("   Activity: ", io=io, context=context, session=session, state=state) or "").lower().strip()
        mapping = {'s': 'study', 'f': 'social', 'm': 'mind'}
        return mapping.get(sub)

    if choice == '0':
        return 'BACK'

    return None
 
def plan_week_ui(
    start_fatigue: int,
    player: Optional[Player],
    coach_order: Optional[CoachOrder] = None,
    *,
    context: Optional[GameContext] = None,
    session=None,
    state=None,
    io: Optional[IOInterface] = None,
):
    """Interactive weekly planner that accounts for squad status + trust."""

    log = io.log if io else print
    prompt_fn = io.prompt if io else input
    wait_fn = io.wait if io else time.sleep

    start_fatigue = start_fatigue or 0
    mandatory_schedule = build_mandatory_schedule(player)

    schedule_grid = [[None for _ in range(3)] for _ in range(7)]
    for (day, slot), action in mandatory_schedule.items():
        schedule_grid[day][slot] = action

    history: List[Tuple[int, int, List[List[Optional[str]]], int, List[Dict[str, object]]]] = []
    skipped_mandatory: List[Dict[str, object]] = []

    day_idx = 0
    slot_idx = 0
    current_fatigue = start_fatigue
    team_snapshot = _team_load_snapshot(player)

    while day_idx < 7:
        progress_snapshot = _calculate_schedule_order_progress(coach_order, schedule_grid)
        render_planning_ui(
            schedule_grid,
            day_idx,
            slot_idx,
            current_fatigue,
            mandatory_schedule,
            coach_order,
            progress_snapshot,
            team_snapshot,
            getattr(player, 'school', None),
            io=io,
        )

        mandatory_action = mandatory_schedule.get((day_idx, slot_idx))
        current_action = schedule_grid[day_idx][slot_idx]
        action = get_slot_choice(current_action, context=context, session=session, state=state, io=io)

        if action == 'EXIT':
            return None, None

        if action == 'BACK':
            if not history:
                log("Cannot go back further.", level="warning")
                wait_fn(1)
                continue
            day_idx, slot_idx, saved_grid, current_fatigue, skipped_mandatory = history.pop()
            schedule_grid = [row[:] for row in saved_grid]
            continue

        if not action:
            continue

        # Coach controls B-team scrimmages; players cannot replace them.
        if mandatory_action == 'b_team_match' and action != mandatory_action:
            log(f"\n{Colour.WARNING}Coach assigned a B-Team scrimmage. You can't change this slot.{Colour.RESET}", level="warning")
            wait_fn(1)
            continue

        if mandatory_action and action != mandatory_action:
            log(f"\n{Colour.FAIL}WARNING: Coach Kataoka is watching.{Colour.RESET}", level="warning")
            log(
                f"Skipping {mandatory_action.replace('_', ' ').title()} will significantly lower Coach Trust."
            )
            confirm = (_resolve_prompt(
                "Are you sure you want to skip? (y/n): ",
                io=io,
                context=context,
                session=session,
                state=state,
                default="n",
            ) or "").strip().lower()
            if confirm != 'y':
                continue
            skipped_mandatory.append(
                {
                    "day": DAYS_OF_WEEK[day_idx],
                    "slot": SLOTS[slot_idx],
                    "expected": mandatory_action,
                    "chosen": action,
                }
            )

        cost = get_action_cost(action)
        new_fatigue = max(0, current_fatigue + cost)
        if new_fatigue > 90:
            log(f"{Colour.FAIL}WARNING: Fatigue will reach {new_fatigue}. High injury risk!{Colour.RESET}", level="warning")
            confirm = (_resolve_prompt(
                "Confirm? (y/n): ",
                io=io,
                context=context,
                session=session,
                state=state,
                default="n",
            ) or "").strip().lower()
            if confirm != 'y':
                continue

        grid_snapshot = [row[:] for row in schedule_grid]
        history.append((day_idx, slot_idx, grid_snapshot, current_fatigue, skipped_mandatory.copy()))
        schedule_grid[day_idx][slot_idx] = action
        current_fatigue = new_fatigue

        slot_idx += 1
        if slot_idx > 2:
            slot_idx = 0
            day_idx += 1

    final_progress = _calculate_schedule_order_progress(coach_order, schedule_grid)
    render_planning_ui(
        schedule_grid,
        7,
        0,
        current_fatigue,
        mandatory_schedule,
        coach_order,
        final_progress,
        team_snapshot,
        getattr(player, 'school', None),
        io=io,
    )
    confirm_exec_raw = (io.prompt(
        f"\n{Colour.GREEN}Schedule Complete.{Colour.RESET} Press Enter to execute or [B] to discard and return: "
    ) if io else input_with_debug(
        f"\n{Colour.GREEN}Schedule Complete.{Colour.RESET} Press Enter to execute or [B] to discard and return: ",
        context=context,
        session=session,
        state=state,
    ))
    if confirm_exec_raw is None:
        return None, None
    confirm_exec = confirm_exec_raw.strip().lower()
    if confirm_exec == 'b':
        return None, None

    return schedule_grid, skipped_mandatory

def execute_schedule_silent(context: GameContext, schedule_grid, current_week, *, rng_seed=None):
    """Execute schedule math without emitting per-slot narration."""

    provider = context.session_provider
    player_repo = SQLAlchemyPlayerRepository(provider)
    team_repo = SQLAlchemyTeamRepository(provider)
    progression_service = SQLAlchemyProgressionService(provider)

    execution = execute_schedule_core(
        context,
        schedule_grid,
        current_week,
        rng_seed=rng_seed,
        player_repo=player_repo,
        team_repo=team_repo,
        progression_service=progression_service,
    )
    summary = _summarize_execution(current_week, execution)
    return execution, summary


def start_week(context: GameContext, current_week: int, state: Optional[GameState] = None) -> bool:
    """Primary entry point for the weekly training phase.

    Returns True when the week was executed, False if the user backed out.
    """
    io = ConsoleIO() if 'ConsoleIO' in globals() else None
    log = io.log if io else print
    prompt = io.prompt if io else input
    wait = io.wait if io else time.sleep
    player, coach_order, exam_summary, event_result = _initialize_week(context, current_week, io=io)
    if not player:
        log("No active player is set. Load a save before planning the week.", level="error")
        return
    _print_weekly_brief(player, current_week, coach_order, io=io)

    if exam_summary:
        letter = score_to_letter_grade(int(exam_summary['score'])) if exam_summary.get('score') is not None else exam_summary.get('grade')
        log(
            f"\n{Colour.CYAN}Exam: {exam_summary['exam_name']} -> {exam_summary['score']} ({letter}){Colour.RESET}",
            level="info",
        )
        log(f" {exam_summary['comment']}")

    if event_result and event_result.summary:
        log(f"\n{Colour.BOLD}Weekly Highlight:{Colour.RESET} {event_result.summary}")

    if not is_academically_eligible(player, player.school):
        needed = required_score_for_school(player.school)
        log(
            f"\n{Colour.WARNING}Academic Warning:{Colour.RESET} Coach expects at least {needed} to keep you eligible.",
            level="warning",
        )
    while True:
        nav = prompt("\n[Enter] Planning | [L] Pitch Lab | [Q] Quit: ").strip().lower()
        if nav in {"", "enter"}:
            break
        if nav == "q":
            return False
        if nav == "l":
            open_pitch_lab(context.session, player, io=io)
        else:
            continue

    start_fatigue = player.fatigue or 0
    schedule_grid, skipped_mandatory = plan_week_ui(
        start_fatigue,
        player,
        coach_order,
        context=context,
        session=context.session if context else None,
        state=state,
        io=io,
    )
    if schedule_grid is None:
        log(f"{Colour.WARNING}Planning cancelled. Returning to Week Prep...{Colour.RESET}", level="warning")
        wait(1)
        return False

    try:
        seed = _schedule_seed(context, current_week)
        execution, summary = execute_schedule_silent(context, schedule_grid, current_week, rng_seed=seed)
    except ValueError as err:
        log(f"Execution aborted: {err}", level="error")
        return False

    summary.add_schedule_note("Player-planned week.")
    summary = _finalize_week_outcomes(
        context,
        current_week=current_week,
        coach_order=coach_order,
        execution=execution,
        skipped_mandatory=skipped_mandatory,
        summary=summary,
        exam_summary=exam_summary,
        event_text=event_text,
    )

    render_weekly_dashboard(summary)
    prompt("Press Enter to continue...")
    return True