import sqlalchemy
from sqlalchemy.orm import sessionmaker
import sys
import os
import random

# Fix Imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.setup_db import School, Player, engine, ScoutingData
from utils import PLAYER_ID 
from ui.ui_display import Colour, clear_screen
from game.scouting_system import get_scouting_info, perform_scout_action

Session = sessionmaker(bind=engine)
session = Session()

DEBUG_MODE = False 

def fmt_stat(value, visible=True):
    return str(value) if visible else "??"

def print_team_roster(school, title_prefix="SCOUTING", view_mode="ACTIVE"):
    """
    Displays a formatted roster.
    view_mode: "ACTIVE" (Jersey 1-18) or "RESERVE" (Jersey 19+ or None)
    """
    clear_screen()
    
    user_p = session.query(Player).get(PLAYER_ID)
    is_my_team = (user_p and user_p.school_id == school.id)
    
    knowledge = 3 if is_my_team else 0
    rivalry = 0
    
    if not is_my_team:
        info = get_scouting_info(school.id)
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
            show_stats = (knowledge >= 3) or DEBUG_MODE
            
            status = "OK"
            if knowledge >= 2:
                if p.injury_days > 0: status = f"{Colour.RED}INJ{Colour.RESET}"
                elif p.fatigue > 50: status = f"{Colour.YELLOW}TRD{Colour.RESET}"

            stats_str = ""
            if p.position == "Pitcher":
                role = p.role[:3].upper() if (p.role and knowledge >=2) else "P"
                stats_str = f"VEL:{fmt_stat(p.velocity, show_stats)} CTR:{fmt_stat(p.control, show_stats)} STA:{fmt_stat(p.stamina, show_stats)}"
            else:
                role = p.position[:2].upper()
                stats_str = f"CON:{fmt_stat(p.contact, show_stats)} PWR:{fmt_stat(p.power, show_stats)} SPD:{fmt_stat(p.speed, show_stats)}"

            num_str = f"#{p.jersey_number}" if (p.jersey_number and p.jersey_number < 99) else "--"
            row_str = f" {num_str:<3} | {role:<4} | {name_display:<22} | {status:<8} | {stats_str:<40}"
            print(row_str)
        
    print("="*95)
    
    # Scouting Actions
    if not is_my_team and knowledge < 3:
        cost = 50000 * (knowledge + 1)
        print(f"{Colour.CYAN}[ACTION] Scout Team (Cost: ¥{cost:,}){Colour.RESET}")
        if input("Purchase Intel? (y/n): ").lower() == 'y':
            user_school = session.query(School).get(user_p.school_id)
            success, msg = perform_scout_action(user_school, school, cost)
            print(msg)
            if success:
                import time; time.sleep(1)
                print_team_roster(school, title_prefix, view_mode) # Refresh

def view_scouting_menu():
    while True:
        clear_screen()
        print(f"\n{Colour.HEADER}--- SCOUTING NETWORK ---{Colour.RESET}")
        
        user_p = session.query(Player).get(PLAYER_ID)
        user_school = session.query(School).get(user_p.school_id)
        print(f"School Budget: ¥{user_school.budget:,}")
        
        print("1. View Active Roster (Top 18)")
        print("2. View Reserves (B-Team)")
        print("3. Scout Rival School")
        print("0. Back")
        
        choice = input("Select: ")
        
        if choice == '1':
            print_team_roster(user_school, "MY TEAM", "ACTIVE")
            input("\n[Press Enter]")
        elif choice == '2':
            print_team_roster(user_school, "MY TEAM", "RESERVE")
            input("\n[Press Enter]")
        elif choice == '3':
            count = session.query(School).count()
            if count > 0:
                rand_idx = random.randint(0, count - 1)
                rand_school = session.query(School).offset(rand_idx).first()
                if rand_school:
                    print_team_roster(rand_school, "RIVAL REPORT", "ACTIVE")
            input("\n[Press Enter]")
        elif choice == '0':
            break

if __name__ == "__main__":
    view_scouting_menu()