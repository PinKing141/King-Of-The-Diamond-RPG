import os

class Colour:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Semantic Aliases
    FAIL = '\033[91m'    # RED
    WARNING = '\033[93m' # YELLOW
    
    # This was the missing line causing your crash:
    gold = '\033[93m'    # Yellow (used for trophies/titles)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def render_screen(conn, player_data):
    """
    Renders the main game HUD for the provided player snapshot.
    """
    clear_screen()
    
    # --- HEADER ---
    print(f"{Colour.HEADER}{'='*60}")
    print(f"{'KOSHIEN: ROAD TO GLORY':^60}")
    print(f"{'='*60}{Colour.RESET}")
    
    # --- DATE & TIME ---
    date_str = f"Year {player_data['current_year']} | Month {player_data['current_month']} | Week {player_data['current_week']}"
    print(f"{Colour.CYAN}{date_str:^60}{Colour.RESET}")
    print("-" * 60)
    
    # --- PLAYER INFO ---
    name_display = f"{player_data['first_name']} {player_data['last_name']}"
    pos_display = f"{player_data['position']}"
    if player_data['jersey_number'] == 1: pos_display += " (ACE)"
    
    print(f" Name: {Colour.BOLD}{name_display:<20}{Colour.RESET} School: {player_data.get('school_name', 'Unknown')}")
    print(f" Role: {pos_display:<20} Grade:  Year {player_data['year']}")
    print("-" * 60)
    
    # --- ATTRIBUTES ---
    def fmt_stat(val):
        return f"{int(val):<3}" 

    print(f"{Colour.BLUE}[ PITCHING ]{Colour.RESET}            {Colour.GREEN}[ BATTING / FIELDING ]{Colour.RESET}")
    print(f" Control : {fmt_stat(player_data.get('control'))}             Power   : {fmt_stat(player_data.get('power'))}")
    print(f" Velocity: {fmt_stat(player_data.get('velocity'))} km/h        Contact : {fmt_stat(player_data.get('contact'))}")
    print(f" Stamina : {fmt_stat(player_data.get('stamina'))}             Speed   : {fmt_stat(player_data.get('running'))}")
    print(f" Break   : {fmt_stat(player_data.get('breaking_ball'))}             Defense : {fmt_stat(player_data.get('fielding'))}")
    
    # --- STATUS BARS ---
    fatigue = int(player_data.get('fatigue', 0))
    morale = int(player_data.get('morale', 50))
    
    if fatigue < 30: f_col = Colour.GREEN
    elif fatigue < 70: f_col = Colour.YELLOW
    else: f_col = Colour.RED
    
    if morale > 80: m_col = Colour.CYAN
    elif morale > 40: m_col = Colour.GREEN
    else: m_col = Colour.RED

    print("-" * 60)
    print(f" Fatigue: {f_col}{'|' * (fatigue // 5)}{Colour.RESET} ({fatigue}%)")
    print(f" Morale : {m_col}{'|' * (morale // 5)}{Colour.RESET} ({morale}%)")
    print("=" * 60)

def display_menu():
    print("\nActions:")
    print(" 1. Plan Week")
    print(" 2. Scouting Report")
    print(" 3. Character Sheet")
    print(" 4. System / Save")