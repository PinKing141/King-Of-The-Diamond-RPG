import sys
import os
import random

# Fix Imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.setup_db import School, Player
from ui.ui_display import Colour, clear_screen
from game.scouting_system import get_scouting_info, perform_scout_action
from game.game_context import GameContext

DEBUG_MODE = False 
KNOWLEDGE_LABELS = ["Unknown", "Basic", "Detailed", "Full"]

GRADE_BUCKETS = [
    (0, "F"),
    (40, "E"),
    (50, "D"),
    (60, "C"),
    (70, "B"),
    (82, "A"),
    (92, "S"),
]


def _grade_index(value: int) -> int:
    idx = 0
    for i, (threshold, _) in enumerate(GRADE_BUCKETS):
        if value >= threshold:
            idx = i
    return min(idx, len(GRADE_BUCKETS) - 1)


def _grade_label(idx: int) -> str:
    return GRADE_BUCKETS[max(0, min(idx, len(GRADE_BUCKETS) - 1))][1]


def format_scouting_result_message(result):
    """Translate a scouting action result into a user-facing string."""
    if result.status == "invalid-selection":
        return "Invalid school selection."

    if result.status == "insufficient-funds":
        have = result.budget_before or 0
        return f"Not enough funds! Need ¥{result.cost_yen:,}, have ¥{have:,}."

    if result.status == "max-knowledge":
        lvl_idx = result.knowledge_before or 0
        lvl = KNOWLEDGE_LABELS[min(lvl_idx, len(KNOWLEDGE_LABELS) - 1)]
        return f"We already have full intel on this team (knowledge: {lvl})."

    if result.status == "success":
        lvl_idx = result.knowledge_after or 0
        lvl = KNOWLEDGE_LABELS[min(lvl_idx, len(KNOWLEDGE_LABELS) - 1)]
        remaining = result.budget_after or 0
        return (
            f"Scouting complete! Knowledge increased to {lvl}. "
            f"Cost: ¥{result.cost_yen:,}. Remaining budget: ¥{remaining:,}."
        )

    return "Scouting action could not be processed."

def fmt_stat(value, knowledge: int) -> str:
    if value is None:
        return "--"
    if DEBUG_MODE or knowledge >= 3:
        return str(int(value))
    if knowledge <= 0:
        return "??"

    base_idx = _grade_index(int(value))
    # Basic intel gets a two-letter range, Detailed gets a tighter single-grade reveal.
    spread = 1 if knowledge == 1 else 0
    low_idx = max(0, base_idx - spread)
    low_label = _grade_label(low_idx)
    high_label = _grade_label(base_idx)
    if low_idx == base_idx:
        return low_label
    return f"{low_label}-{high_label}"

def print_team_roster(session, school, active_player_id, title_prefix="SCOUTING", view_mode="ACTIVE"):
    """
    Displays a formatted roster.
    view_mode: "ACTIVE" (Jersey 1-18) or "RESERVE" (Jersey 19+ or None)
    """
    clear_screen()
    
    user_p = session.get(Player, active_player_id) if active_player_id else None
    is_my_team = (user_p and user_p.school_id == school.id)
    
    knowledge = 3 if is_my_team else 0
    rivalry = 0
    
    if not is_my_team:
        info = get_scouting_info(school.id, session=session)
        knowledge = info.knowledge_level
        rivalry = info.rivalry_score

    print("\n" + "="*95)
    print(f"{title_prefix} [{view_mode}]: {school.name.upper()}")
    
    loc = school.prefecture if knowledge >= 1 else "??"
    style = school.philosophy if knowledge >= 1 else "??"
    rank = f"{school.prestige}/100" if knowledge >= 1 else "??"
    
    print(f"Loc: {loc}  |  Style: {style}")
    print(f"Rank: {rank}")
    
    if rivalry > 5:
        print(f"{Colour.RED}*** BITTER RIVAL (Heat: {rivalry}) ***{Colour.RESET}")
        
    print("="*95)
    
    # Fetch players
    all_players = session.query(Player).filter_by(school_id=school.id).order_by(Player.jersey_number).all()
    
    # Filter based on mode
    display_players = []
    
    if view_mode == "ACTIVE":
        # Get players with jersey 1-18
        display_players = [p for p in all_players if p.jersey_number and p.jersey_number <= 18]
        display_players.sort(key=lambda p: p.jersey_number)
    else:
        # Get players with jersey > 18 or None
        display_players = [p for p in all_players if not p.jersey_number or p.jersey_number > 18]
        # Sort reserves by position then name
        display_players.sort(key=lambda p: (p.position, p.name))

    if not display_players:
        print(f"   (No players found in {view_mode} list)")
    else:
        header = f" {'NO':<3} | {'POS':<4} | {'NAME':<22} | {'STS':<8} | {'KEY ATTRIBUTES':<40}"
        print(header)
        print("-" * len(header))

        for p in display_players:
            # Name Masking
            name_display = p.name if knowledge >= 1 else "Unknown Player"
            if len(name_display) > 22: name_display = name_display[:20] + '.'
            
            # Stats Masking
            status = "OK"
            if knowledge >= 2:
                if p.injury_days > 0: status = f"{Colour.RED}INJ{Colour.RESET}"
                elif p.fatigue > 50: status = f"{Colour.YELLOW}TRD{Colour.RESET}"

            stats_str = ""
            if p.position == "Pitcher":
                role = p.role[:3].upper() if (p.role and knowledge >=2) else "P"
                stats_str = (
                    f"VEL:{fmt_stat(p.velocity, knowledge)} "
                    f"CTR:{fmt_stat(p.control, knowledge)} "
                    f"STA:{fmt_stat(p.stamina, knowledge)}"
                )
            else:
                role = p.position[:2].upper()
                stats_str = (
                    f"CON:{fmt_stat(p.contact, knowledge)} "
                    f"PWR:{fmt_stat(p.power, knowledge)} "
                    f"SPD:{fmt_stat(p.speed, knowledge)}"
                )

            num_str = f"#{p.jersey_number}" if (p.jersey_number and p.jersey_number < 99) else "--"
            row_str = f" {num_str:<3} | {role:<4} | {name_display:<22} | {status:<8} | {stats_str:<40}"
            print(row_str)
        
    print("="*95)
    
    # Scouting Actions
    if not is_my_team and knowledge < 3:
        cost = 50000 * (knowledge + 1)
        print(f"{Colour.CYAN}[ACTION] Scout Team (Cost: ¥{cost:,}){Colour.RESET}")
        if input("Purchase Intel? (y/n): ").lower() == 'y':
            user_school = session.get(School, user_p.school_id)
            result = perform_scout_action(session, user_school.id, school.id, cost)
            print(format_scouting_result_message(result))
            if result.success:
                import time; time.sleep(1)
                session.expire_all()
                print_team_roster(session, school, active_player_id, title_prefix, view_mode) # Refresh

def view_scouting_menu(context: GameContext):
    if context.player_id is None:
        print("No active player found.")
        input("\n[Press Enter]")
        return

    context.refresh_session()
    session = context.session

    while True:
        clear_screen()
        print(f"\n{Colour.HEADER}--- SCOUTING NETWORK ---{Colour.RESET}")
        
        user_p = session.get(Player, context.player_id)
        if not user_p:
            print("No active player found.")
            input("\n[Press Enter]")
            return
        user_school = session.get(School, user_p.school_id)
        print(f"School Budget: ¥{user_school.budget:,}")
        
        print("1. View Active Roster (Top 18)")
        print("2. View Reserves (B-Team)")
        print("3. Scout Rival School")
        print("0. Back")
        
        choice = input("Select: ")
        
        if choice == '1':
            print_team_roster(session, user_school, context.player_id, "MY TEAM", "ACTIVE")
            input("\n[Press Enter]")
        elif choice == '2':
            print_team_roster(session, user_school, context.player_id, "MY TEAM", "RESERVE")
            input("\n[Press Enter]")
        elif choice == '3':
            count = session.query(School).count()
            if count > 0:
                rand_idx = random.randint(0, count - 1)
                rand_school = session.query(School).offset(rand_idx).first()
                if rand_school:
                    print_team_roster(session, rand_school, context.player_id, "RIVAL REPORT", "ACTIVE")
            input("\n[Press Enter]")
        elif choice == '0':
            break
        else:
            continue
        session.expire_all()

if __name__ == "__main__":
    raise SystemExit("Launch the scouting menu from the main game loop.")