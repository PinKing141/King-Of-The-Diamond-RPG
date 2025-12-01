import time
import sys
from collections import defaultdict
from typing import Optional

from database.setup_db import Player
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

# --- CONSTANTS ---
# Costs are used for UI forecasting only; actual costs are in training_logic.py
COSTS = {
    'rest': -15, 
    'team_practice': 20, 
    'practice_match': 35,
    'b_team_match': 25, # New Cost for B-Team
    'train_heavy': 15, 
    'train_light': 10, 
    'study': 5,
    'social': 5,
}

MANDATORY_SCHEDULE = {
    (3, 1): 'team_practice', # THU Afternoon
    (5, 0): 'practice_match', # SAT Morning
    (5, 1): 'practice_match', # SAT Afternoon
}


def _get_active_player(context: GameContext) -> Optional[Player]:
    if context.player_id is None:
        return None
    return context.session.get(Player, context.player_id)

# --- HELPER FUNCTIONS ---

def get_action_cost(action_key):
    if not action_key: return 0
    if 'power' in action_key or 'speed' in action_key or 'stamina' in action_key:
        return COSTS['train_heavy']
    if 'control' in action_key or 'contact' in action_key or 'fielding' in action_key:
        return COSTS['train_light']
    return COSTS.get(action_key, 0)

def render_planning_ui(schedule_state, current_day_idx, current_slot_idx, current_fatigue):
    """
    Draws the weekly calendar grid with the current selection cursor.
    """
    clear_screen()
    print(f"{Colour.HEADER}=== WEEKLY PLANNING ==={Colour.RESET}")
    
    header = "      " + " ".join([f"{d[:3]:^5}" for d in DAYS_OF_WEEK])
    print(header)
    
    for s_idx, slot_name in enumerate(SLOTS):
        row_str = f"{slot_name[0].upper()} | "
        for d_idx in range(7):
            action = schedule_state[d_idx][s_idx]
            
            if (d_idx, s_idx) == (current_day_idx, current_slot_idx):
                symbol = f"{Colour.CYAN}[ ? ]{Colour.RESET}"
            elif action:
                if action == 'rest': symbol = f"{Colour.GREEN}  R  {Colour.RESET}"
                elif 'team' in action: symbol = f"{Colour.YELLOW}  T  {Colour.RESET}"
                elif 'match' in action and 'b_team' not in action: symbol = f"{Colour.RED}  M  {Colour.RESET}"
                elif 'b_team' in action: symbol = f"{Colour.gold}  B  {Colour.RESET}" # B-Team Symbol
                elif 'train' in action: symbol = f"{Colour.CYAN}  Tr {Colour.RESET}"
                elif 'study' in action: symbol = f"{Colour.BLUE}  St {Colour.RESET}"
                elif 'social' in action: symbol = f"{Colour.BLUE}  So {Colour.RESET}"
                else: symbol = "  .  "
            else:
                symbol = "  .  "
            
            row_str += f"{symbol} "
        print(row_str)
        
    print("-" * 60)
    
    f_col = Colour.GREEN
    if current_fatigue > 50: f_col = Colour.YELLOW
    if current_fatigue > 90: f_col = Colour.RED
    
    print(f"Projected Fatigue: {f_col}{current_fatigue}/100{Colour.RESET}")
    if current_fatigue > 100:
        print(f"{Colour.FAIL}!!! DANGER: INJURY RISK EXTREME !!!{Colour.RESET}")
    elif current_fatigue > 85:
        print(f"{Colour.WARNING}Warning: High injury risk.{Colour.RESET}")
        
    print("-" * 60)
    
    if current_day_idx < 7:
        curr_day_name = DAYS_OF_WEEK[current_day_idx]
        curr_slot_name = SLOTS[current_slot_idx]
        print(f"Scheduling: {Colour.BOLD}{curr_day_name} {curr_slot_name}{Colour.RESET}")
    else:
        print(f"Scheduling: {Colour.BOLD}Review{Colour.RESET}")

def get_slot_choice():
    """
    Prompts user for an action selection for a single slot.
    """
    print("\nSelect Action:")
    print(f" 1. {Colour.CYAN}TRAIN{Colour.RESET} (Drills)")
    print(f" 2. {Colour.GREEN}REST{Colour.RESET}  (Recover)")
    print(f" 3. {Colour.BLUE}LIFE{Colour.RESET}  (Study/Social)")
    print(f" 4. {Colour.YELLOW}MATCH{Colour.RESET}  (B-Team Scrimmage)") # Added Option 4
    print(" 0. BACK")
    
    choice = input(">> ").strip()
    
    if choice == '1':
        print("   [P]ower  [S]peed  [St]amina  [C]ontrol  [Co]ntact  [B]ack")
        sub = input("   Drill: ").lower().strip()
        if sub == 'p': return 'train_power'
        if sub == 's': return 'train_speed'
        if sub == 'st': return 'train_stamina'
        if sub == 'c': return 'train_control'
        if sub == 'co': return 'train_contact'
        if sub == 'b': return None
        return None
        
    elif choice == '2':
        return 'rest'
        
    elif choice == '3':
        print("   [S]tudy  [F]riends  [M]ind  [B]ack")
        sub = input("   Activity: ").lower().strip()
        if sub == 's': return 'study'
        if sub == 'f': return 'social'
        if sub == 'm': return 'mind'
        if sub == 'b': return None
        return None
        
    elif choice == '4':
        return 'b_team_match' # Return the new action key
        
    elif choice == '0':
        return 'BACK'
        
    return None

def plan_week_ui(start_fatigue: int):
    """
    Runs the interactive UI for the user to plan their week.
    Returns the completed schedule grid.
    """
    # Default to 0 if no fatigue found
    start_fatigue = start_fatigue or 0
    
    # Initialize Grid with Mandatory Events
    schedule_grid = [[None for _ in range(3)] for _ in range(7)]
    for (d, s), action in MANDATORY_SCHEDULE.items():
        schedule_grid[d][s] = action

    history = []
    
    day_idx = 0
    slot_idx = 0
    current_fatigue = start_fatigue

    while day_idx < 7:
        is_mandatory = (day_idx, slot_idx) in MANDATORY_SCHEDULE
        
        if is_mandatory:
            action = MANDATORY_SCHEDULE[(day_idx, slot_idx)]
            cost = get_action_cost(action)
            grid_snapshot = [row[:] for row in schedule_grid]
            history.append((day_idx, slot_idx, grid_snapshot, current_fatigue))
            current_fatigue = max(0, current_fatigue + cost)
            
            # Auto-advance
            slot_idx += 1
            if slot_idx > 2:
                slot_idx = 0
                day_idx += 1
            continue

        render_planning_ui(schedule_grid, day_idx, slot_idx, current_fatigue)
        
        action = get_slot_choice()
        
        if action == 'BACK':
            if not history:
                print("Cannot go back further.")
                time.sleep(1)
                continue
            prev_state = history.pop()
            day_idx, slot_idx, saved_grid, current_fatigue = prev_state
            schedule_grid = [row[:] for row in saved_grid]
            
            # Retrace back over mandatory slots if necessary
            while (day_idx, slot_idx) in MANDATORY_SCHEDULE:
                if not history: break
                prev_state = history.pop()
                day_idx, slot_idx, saved_grid, current_fatigue = prev_state
                schedule_grid = [row[:] for row in saved_grid]
            continue
            
        if action:
            cost = get_action_cost(action)
            new_fatigue = max(0, current_fatigue + cost)
            
            if new_fatigue > 90:
                print(f"{Colour.FAIL}WARNING: Fatigue will reach {new_fatigue}. High injury risk!{Colour.RESET}")
                confirm = input("Confirm? (y/n): ").lower()
                if confirm != 'y': continue

            grid_snapshot = [row[:] for row in schedule_grid]
            history.append((day_idx, slot_idx, grid_snapshot, current_fatigue))
            schedule_grid[day_idx][slot_idx] = action
            current_fatigue = new_fatigue
            slot_idx += 1
            if slot_idx > 2:
                slot_idx = 0
                day_idx += 1
        else: pass

    render_planning_ui(schedule_grid, 7, 0, current_fatigue)
    input(f"\n{Colour.GREEN}Schedule Complete. Press Enter to Execute.{Colour.RESET}")
    
    return schedule_grid

def execute_schedule(context: GameContext, schedule_grid, current_week):
    """Call the core executor then render its structured output."""
    print(f"\n=== EXECUTING WEEK {current_week} SCHEDULE ===")

    try:
        execution = execute_schedule_core(context, schedule_grid, current_week)
    except ValueError as err:
        print(f"Execution aborted: {err}")
        return

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

            if slot_result.opponent_name:
                print(f"      ⚾ GAME START: vs {slot_result.opponent_name}")
                if slot_result.match_result:
                    color = Colour.GREEN if slot_result.match_result == 'WON' else Colour.FAIL
                    score_text = slot_result.match_score or "N/A"
                    print(
                        f"      🏁 RESULT: {color}{slot_result.match_result}{Colour.RESET} ({score_text})"
                    )
            if slot_result.error:
                print(f"      {Colour.WARNING}{slot_result.error}{Colour.RESET}")

    if execution.warnings:
        print("\nWarnings:")
        for warn in execution.warnings:
            print(f" - {warn}")

# --- MAIN ENTRY POINT ---

def start_week(context: GameContext, current_week):
    """
    Orchestrates the activities for a single week of the game.
    """
    print(f"\n=== WEEK {current_week} BEGINS ===")
    
    # 1. RUN ROSTER AI (The New Brain)
    # Before any user input, coaches across Japan analyze their teams.
    print(" > Coaches are setting lineups...")
    run_roster_logic() 
    
    # 2. TRIGGER RANDOM EVENTS (The "Living World" update)
    # Happen before user plans their week so they can react to morale changes etc.
    trigger_random_event(context, current_week=current_week)
    
    # 3. USER PLANNING
    # User decides what to do this week
    player = _get_active_player(context)
    if not player:
        print(f"{Colour.FAIL}Active player missing. Skipping scheduling.{Colour.RESET}")
        return

    seed_relationships(context.session, player)

    exam_result = maybe_run_academic_exam(player, current_week)
    if exam_result:
        context.session.commit()
        print(f"\n{Colour.BLUE}ACADEMICS: {exam_result['exam_name']}{Colour.RESET}")
        print(f" Score {exam_result['score']} ({exam_result['grade']}) — {exam_result['comment']}")
        if exam_result.get('grade') in {'D', 'F'}:
            run_dialogue_event("coach_academic_suspension", player, player.school)

    passing_score = required_score_for_school(player.school)

    if not is_academically_eligible(player, player.school):
        current_score = int(round(player.test_score or player.academic_skill or 0))
        print(
            f"{Colour.WARNING}Academic Suspension: Score {current_score}. Need {passing_score}+ to dress for games.{Colour.RESET}"
        )

    start_fatigue = player.fatigue if player.fatigue is not None else 0

    final_schedule = plan_week_ui(start_fatigue)
    
    # 4. EXECUTE WEEK
    # Run the days, update stats, play the matches
    execute_schedule(context, final_schedule, current_week)

    context.clear_all_temp_effects()
    
    print(f"=== WEEK {current_week} COMPLETE ===\n")