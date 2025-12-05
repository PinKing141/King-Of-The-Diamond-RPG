import json
import time
import sys
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from database.setup_db import Player, GameState
from sqlalchemy.orm import object_session
from game.constants import (
    ACTION_COSTS,
    ACTION_METADATA,
    ACTION_METADATA_DEFAULT,
    FIRST_STRING_WEEKEND,
    HEAVY_TRAINING_ACTIONS,
    LIGHT_TRAINING_ACTIONS,
    MANDATORY_TEAM_POLICY,
    SECOND_STRING_WEEKEND,
    SQUAD_FIRST_STRING,
    SQUAD_SECOND_STRING,
)
from world.roster_manager import run_roster_logic
# Import the bridge function from the new match engine location
from ui.ui_display import Colour, clear_screen
# Import the new Event Manager
from game.event_manager import trigger_random_event
from game.game_context import GameContext
from game.relationship_manager import seed_relationships
from game.academic_system import (
    maybe_run_academic_exam,
    is_academically_eligible,
    required_score_for_school,
)
from game.dialogue_manager import run_dialogue_event
from game.weekly_scheduler_core import (
    DAYS_OF_WEEK,
    SLOTS,
    execute_schedule_core,
)


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
            "actions": ["team_practice", "practice_match", "b_team_match"],
            "count": 2,
        },
        reward_trust=5,
        reward_ability_points=2,
    ),
)

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


def build_mandatory_schedule(player: Optional[Player]) -> Dict[Tuple[int, int], str]:
    base = dict(MANDATORY_TEAM_POLICY)
    squad = _infer_squad_status(player)
    weekend = FIRST_STRING_WEEKEND if squad == SQUAD_FIRST_STRING else SECOND_STRING_WEEKEND
    base.update(weekend)
    return base


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
        except Exception:
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
    except Exception:
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


def _print_weekly_brief(player: Player, current_week: int, coach_order: Optional[CoachOrder] = None) -> None:
    school = getattr(player, 'school', None)
    coach = getattr(school, 'coach', None) if school else None
    squad = _infer_squad_status(player)
    fatigue = player.fatigue or 0
    morale = player.morale or 60
    trust = player.trust_baseline or 50
    academic_score = player.test_score if player.test_score is not None else (player.academic_skill or 0)
    target_score = required_score_for_school(school)

    clear_screen()
    print(f"{Colour.HEADER}=== WEEK {current_week}: TRAINING PREP ==={Colour.RESET}")
    if school:
        print(f"School: {school.name} ({school.prefecture})")
    if coach:
        print(f"Coach: {coach.name} | Expectations: {'First-String' if squad == SQUAD_FIRST_STRING else 'Second-String'}")
    print(f"Player: {player.name or 'You'} | Position: {player.position} | Year {player.year}")
    print(f"Fatigue: {fatigue}/100 | Morale: {morale}")
    ability_points = getattr(player, 'ability_points', 0) or 0
    print(f"Coach Trust Baseline: {trust} | Ability Points: {ability_points}")
    print(f"Academic Standing: {academic_score} (Need {target_score}+ to stay eligible)")
    if coach_order:
        req_text = _describe_order_requirement(coach_order)
        print(
            f"Coach's Orders: {coach_order.description}"
        )
        print(
            f"  Needs: {req_text} | Reward: +{coach_order.reward_trust} Trust, +{coach_order.reward_ability_points} Ability"
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
):
    """Draws the weekly calendar grid with action metadata + cursor focus."""

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

    clear_screen()
    print(f"{Colour.HEADER}=== WEEKLY PLANNING ==={Colour.RESET}")

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
        print(
            f" Team Load {badge}  Fatigue {avg_fatigue:5.1f}% | Stamina {avg_stamina:5.1f}  — {status}"
        )
        if not rest_lock:
            print(
                f"  Cushion: {max(0.0, 65.0 - avg_fatigue):4.1f} fatigue pts / {max(0.0, avg_stamina - 55.0):4.1f} stamina pts"
            )
        else:
            print("  Coaches will cancel optional workouts until the roster recovers.")

    header = "      " + " ".join([f"{d[:3]:^6}" for d in DAYS_OF_WEEK])
    print(header)

    for s_idx, slot_name in enumerate(SLOTS):
        row_str = f"{slot_name[0].upper()} | "
        for d_idx in range(7):
            action = schedule_state[d_idx][s_idx]
            is_cursor = (d_idx, s_idx) == (current_day_idx, current_slot_idx)
            is_mandatory = (d_idx, s_idx) in mandatory_schedule
            row_str += _slot_token(action, is_cursor, is_mandatory) + " "
        print(row_str)

    print("-" * 72)

    f_col = Colour.GREEN
    if current_fatigue > 50:
        f_col = Colour.YELLOW
    if current_fatigue > 90:
        f_col = Colour.RED

    print(f"Projected Fatigue: {f_col}{current_fatigue}/100{Colour.RESET}")
    if current_fatigue > 100:
        print(f"{Colour.FAIL}!!! DANGER: INJURY RISK EXTREME !!!{Colour.RESET}")
    elif current_fatigue > 85:
        print(f"{Colour.WARNING}Warning: High injury risk.{Colour.RESET}")

    focus_label = "Review" if current_day_idx >= 7 else f"{DAYS_OF_WEEK[current_day_idx]} {SLOTS[current_slot_idx]}"
    print(f"Planning Focus: {Colour.BOLD}{focus_label}{Colour.RESET}")

    if current_day_idx < 7:
        planned_action = schedule_state[current_day_idx][current_slot_idx]
        fallback_action = mandatory_schedule.get((current_day_idx, current_slot_idx))
        focus_action = planned_action or fallback_action
        if focus_action:
            meta = ACTION_METADATA.get(_action_meta_key(focus_action), ACTION_METADATA_DEFAULT)
            desc = meta.get("desc") or "No description"
            print(f"Selected Slot Effect: {Colour.BOLD}{desc}{Colour.RESET}")
            if fallback_action and planned_action != fallback_action:
                print(
                    f"{Colour.WARNING}Coach expects {fallback_action.replace('_', ' ').title()} here.{Colour.RESET}"
                )
    if coach_order:
        req_text = _describe_order_requirement(coach_order)
        print(
            f"Coach's Orders: {Colour.BOLD}{coach_order.description}{Colour.RESET} ({req_text})"
        )
        print(
            f" Reward: +{coach_order.reward_trust} Trust / +{coach_order.reward_ability_points} Ability Points"
        )
        if order_progress:
            progress = order_progress.get("progress", 0)
            target = order_progress.get("target", 0)
            remaining = order_progress.get("remaining", max(0, target - progress))
            status_colour = Colour.GREEN if progress >= target and target else Colour.CYAN
            status_label = "Completed" if progress >= target and target else f"{remaining} to go"
            print(
                f" Progress: {status_colour}{progress}/{target}{Colour.RESET} ({status_label})"
            )

def get_slot_choice(current_action: Optional[str]) -> Optional[str]:
    """Prompts the user for an action selection, defaulting to the current value."""
    print("\nSelect Action (Enter = keep current plan):")
    if current_action:
        print(f" Current: {current_action.replace('_', ' ').title()}")
    print(f" 1. {Colour.CYAN}TRAIN{Colour.RESET} (Drills)")
    print(f" 2. {Colour.GREEN}REST{Colour.RESET}  (Recover)")
    print(f" 3. {Colour.BLUE}LIFE{Colour.RESET}  (Study/Social)")
    print(f" 4. {Colour.YELLOW}MATCH{Colour.RESET}  (B-Team Scrimmage)")
    print(" 0. BACK")

    choice = input(">> ").strip().lower()
    if choice == "":
        return current_action

    if choice == '1':
        print("   [P]ower  [S]peed  [St]amina  [C]ontrol  [Co]ntact  [B]ack")
        sub = input("   Drill: ").lower().strip()
        mapping = {
            'p': 'train_power',
            's': 'train_speed',
            'st': 'train_stamina',
            'c': 'train_control',
            'co': 'train_contact',
        }
        return mapping.get(sub)

    if choice == '2':
        return 'rest'

    if choice == '3':
        print("   [S]tudy  [F]riends  [M]ind  [B]ack")
        sub = input("   Activity: ").lower().strip()
        mapping = {'s': 'study', 'f': 'social', 'm': 'mind'}
        return mapping.get(sub)

    if choice == '4':
        return 'b_team_match'

    if choice == '0':
        return 'BACK'

    return None
 
def plan_week_ui(start_fatigue: int, player: Optional[Player], coach_order: Optional[CoachOrder] = None):
    """Interactive weekly planner that accounts for squad status + trust."""

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
        )

        mandatory_action = mandatory_schedule.get((day_idx, slot_idx))
        current_action = schedule_grid[day_idx][slot_idx]
        action = get_slot_choice(current_action)

        if action == 'BACK':
            if not history:
                print("Cannot go back further.")
                time.sleep(1)
                continue
            day_idx, slot_idx, saved_grid, current_fatigue, skipped_mandatory = history.pop()
            schedule_grid = [row[:] for row in saved_grid]
            continue

        if not action:
            continue

        if mandatory_action and action != mandatory_action:
            print(f"\n{Colour.FAIL}WARNING: Coach Kataoka is watching.{Colour.RESET}")
            print(
                f"Skipping {mandatory_action.replace('_', ' ').title()} will significantly lower Coach Trust."
            )
            confirm = input("Are you sure you want to skip? (y/n): ").strip().lower()
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
            print(f"{Colour.FAIL}WARNING: Fatigue will reach {new_fatigue}. High injury risk!{Colour.RESET}")
            confirm = input("Confirm? (y/n): ").strip().lower()
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
    )
    input(f"\n{Colour.GREEN}Schedule Complete. Press Enter to Execute.{Colour.RESET}")

    return schedule_grid, skipped_mandatory

def execute_schedule(context: GameContext, schedule_grid, current_week):
    """Call the core executor then render its structured output."""
    print(f"\n=== EXECUTING WEEK {current_week} SCHEDULE ===")

    try:
        execution = execute_schedule_core(context, schedule_grid, current_week)
    except ValueError as err:
        print(f"Execution aborted: {err}")
        return None

    grouped = defaultdict(list)
    for result in execution.results:
        grouped[result.day_index].append(result)

    for day_idx in sorted(grouped.keys()):
        print(f"\n>> {DAYS_OF_WEEK[day_idx]}")
        for slot_result in sorted(grouped[day_idx], key=lambda r: r.slot_index):
            action_label = slot_result.action.replace('_', ' ').title()
            print(f"   [{SLOTS[slot_result.slot_index]}] {action_label}...", end="")
            sys.stdout.flush()
            time.sleep(0.2)
            print(f" {slot_result.training_summary}")

            details = slot_result.training_details or {}
            if details.get("stat_changes"):
                stat_fragment = ", ".join(
                    f"{k}+{round(v,2)}" for k, v in details["stat_changes"].items()
                )
                print(f"      Stats: {stat_fragment}")
            xp_details = details.get("xp_gains") or {}
            if xp_details:
                xp_fragment = ", ".join(
                    f"{k}+{round(v,2)}xp" for k, v in xp_details.items()
                )
                print(f"      XP: {xp_fragment}")
            breakthrough = details.get("breakthrough")
            if breakthrough:
                stat_label = breakthrough['stat'].replace('_', ' ').title()
                print(f"      🔥 Breakthrough in {stat_label}!")

            if slot_result.opponent_name:
                matchup = slot_result.opponent_name
                if 'b_team' in slot_result.action:
                    matchup = f"{matchup} (B)"
                print(f"      ⚾ GAME START: vs {matchup}")
                if slot_result.match_result:
                    color = Colour.GREEN if slot_result.match_result == 'WON' else Colour.FAIL
                    score_text = slot_result.match_score or "N/A"
                    print(
                        f"      🏁 RESULT: {color}{slot_result.match_result}{Colour.RESET} ({score_text})"
                    )
            if slot_result.error:
                print(f"      {Colour.WARNING}{slot_result.error}{Colour.RESET}")

    return execution


def start_week(context: GameContext, current_week: int) -> None:
    """Primary entry point for the weekly training phase."""
    player = _get_active_player(context)
    if not player:
        print("No active player is set. Load a save before planning the week.")
        return

    # Reset one-week modifiers so fresh effects can be applied.
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

    trigger_random_event(context, current_week)

    player = _get_active_player(context)
    coach_order = _select_coach_order(player, current_week)
    _print_weekly_brief(player, current_week, coach_order)

    if exam_summary:
        print(
            f"\n{Colour.CYAN}Exam: {exam_summary['exam_name']} -> {exam_summary['score']} ({exam_summary['grade']}){Colour.RESET}"
        )
        print(f" {exam_summary['comment']}")

    if not is_academically_eligible(player, player.school):
        needed = required_score_for_school(player.school)
        print(
            f"\n{Colour.WARNING}Academic Warning:{Colour.RESET} Coach expects at least {needed} to keep you eligible."
        )

    input("\nPress Enter to open the planning board...")

    start_fatigue = player.fatigue or 0
    schedule_grid, skipped_mandatory = plan_week_ui(start_fatigue, player, coach_order)

    execution = execute_schedule(context, schedule_grid, current_week)
    if not execution:
        return

    player = _get_active_player(context)
    order_progress = _evaluate_order_progress(coach_order, execution.results)
    reward_delta = {"trust": 0, "ability_points": 0}
    if coach_order and order_progress:
        completed = bool(order_progress.get("completed"))
        progress = order_progress.get("progress", 0)
        target = order_progress.get("target", 0)
        if completed:
            trust_gain = coach_order.reward_trust
            ability_gain = coach_order.reward_ability_points
            old_trust = player.trust_baseline or 50
            player.trust_baseline = min(100, old_trust + trust_gain)
            player.ability_points = (player.ability_points or 0) + ability_gain
            session.add(player)
            reward_delta = {"trust": trust_gain, "ability_points": ability_gain}
            print(
                f"\n{Colour.GREEN}Coach's Orders complete!{Colour.RESET} Trust +{trust_gain}, Ability Points +{ability_gain}."
            )
        else:
            print(
                f"\n{Colour.WARNING}Coach's Orders incomplete.{Colour.RESET} Progress {progress}/{target}."
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

        print(f"\n{Colour.WARNING}Coach Kataoka noted the skipped obligations.{Colour.RESET}")
        print(
            f" Coach Trust {Colour.FAIL}-{penalty_payload['trust_penalty']}{Colour.RESET} (Baseline now {penalty_payload['new_trust']})."
        )
        if penalty_payload['morale_penalty']:
            print(
                f" Morale {Colour.FAIL}-{penalty_payload['morale_penalty']}{Colour.RESET} — teammates question your commitment."
            )
        print(" Details:")
        for slot in penalty_payload['entries']:
            expected = _format_action_label(slot.get('expected'))
            chosen = _format_action_label(slot.get('chosen'))
            print(f"  • {slot['day']} {slot['slot']}: expected {expected} -> planned {chosen}")
        input("\nPress Enter to continue...")
    else:
        session.commit()