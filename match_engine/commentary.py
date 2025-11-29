import time
import sys
import random
from ui.ui_display import Colour

# --- COMMENTARY POOLS ---
STRIKEOUT_PHRASES = [
    "He froze him with a backdoor slider!",
    "Swung at a high heater! Sit down!",
    "Got him looking! A absolute painting on the corner.",
    "Three pitches, three strikes. Good morning, good afternoon, good night!",
    "He chased the breaking ball in the dirt."
]

HOMERUN_PHRASES = [
    "IT IS HIGH! IT IS FAR! IT IS GONE!",
    "That ball was absolutely crushed! A no-doubter!",
    "Goodbye baseball! A moonshot to left field!",
    "Upper deck! What power!",
    "The outfielder didn't even move. Home Run!"
]

HIT_PHRASES = [
    "A sharp liner into the gap!",
    "Hard ground ball past the diving shortstop.",
    "He bloops it over the infield for a base hit.",
    "Smoked down the line! Fair ball!",
    "A rocket off the wall!"
]

def type_writer(text, speed=0.01):
    """Effect to print text slightly like a typewriter."""
    print(text)
    # Uncomment for slow effect (can be annoying in long games)
    # for char in text:
    #     sys.stdout.write(char)
    #     sys.stdout.flush()
    #     time.sleep(speed)
    # print("")

def display_state(state, pitcher, batter):
    """
    Visualizes the current game state: Inning, Score, Diamond, Count.
    """
    print("\n" + "="*60)
    # Use 'name' attribute for V2 Schema compatibility
    away_name = getattr(state.away_team, 'name', 'Away')
    home_name = getattr(state.home_team, 'name', 'Home')
    
    print(f" {away_name[:3]} {state.away_score}  -  {state.home_score} {home_name[:3]}   |   {state.top_bottom} {state.inning}")
    print("="*60)
    
    # Diamond Visualization
    r1 = f"{Colour.RED}X{Colour.RESET}" if state.runners[0] else " "
    r2 = f"{Colour.RED}X{Colour.RESET}" if state.runners[1] else " "
    r3 = f"{Colour.RED}X{Colour.RESET}" if state.runners[2] else " "
    
    print(f"      [{r2}]")
    print(f"     /   \\")
    print(f"   [{r3}]   [{r1}]")
    print(f"     \\   /")
    print(f"      [ ]")
    
    # Matchup Info
    # Check conditioning for flavor text (Optional)
    p_cond = ""
    if hasattr(pitcher, 'conditioning') and pitcher.conditioning > 70:
        p_cond = f"{Colour.GREEN}(Sharp){Colour.RESET}"
    
    b_cond = ""
    if hasattr(batter, 'conditioning') and batter.conditioning > 70:
        b_cond = f"{Colour.GREEN}(Focused){Colour.RESET}"

    # Pitcher info (Arm slot might be missing in V2 schema if not generated, handle gracefully)
    arm_slot = getattr(pitcher, 'arm_slot', 'Overhand') 
    
    # Use 'name' or 'last_name' depending on schema. V2 uses 'name' as full name usually.
    p_name = getattr(pitcher, 'name', getattr(pitcher, 'last_name', 'Pitcher'))
    b_name = getattr(batter, 'name', getattr(batter, 'last_name', 'Batter'))
    
    print(f"\n PITCHER: {p_name} {p_cond} ({arm_slot})")
    print(f" BATTER:  {b_name} {b_cond} (Pow {batter.power} / Con {batter.contact})")
    print(f" COUNT:   {state.balls}-{state.strikes}  |  OUTS: {state.outs}")
    print("-" * 60)

def announce_pitch(pitch_result):
    vel_str = f"{pitch_result.velocity:.1f} km/h"
    
    if pitch_result.outcome == "Ball":
        print(f" > {pitch_result.pitch_name} ({vel_str}) ... Ball {pitch_result.description}.")
        
    elif pitch_result.outcome == "Strike":
        desc = pitch_result.description
        if desc == "Swinging Miss":
            desc = f"{Colour.YELLOW}Swinging Miss{Colour.RESET}"
        elif desc == "Looking":
            desc = f"{Colour.CYAN}Looking{Colour.RESET}"
            
        print(f" > {pitch_result.pitch_name} ({vel_str}) ... STRIKE! ({desc})")
        
    elif pitch_result.outcome == "Foul":
        print(f" > {pitch_result.pitch_name} ... Fouled off.")
        
    elif pitch_result.outcome == "InPlay":
        print(f" > {pitch_result.pitch_name} ... {Colour.BOLD}CONTACT!{Colour.RESET}")

def announce_play(contact_result):
    if contact_result.hit_type == "Out":
        print(f"   >> {contact_result.description}")
        
        # Add flavor for strikeouts
        if "Strikeout" in contact_result.description:
             print(f"   >> {random.choice(STRIKEOUT_PHRASES)}")

    elif contact_result.hit_type == "HR":
        # ASCII Art for Home Run
        print(f"\n{Colour.RED}")
        print(r"       _   _  ____  __  __  ___   ____  _   _  _   _ ")
        print(r"      | | | |/ __ \|  \/  || __| |  _ \| | | || \ | |")
        print(r"      | |_| | |  | | \  / || _|  | |_) | | | ||  \| |")
        print(r"      |  _  | |__| | |\/| || |__ |  _ <| |_| || |\  |")
        print(r"      |_| |_|\____/|_|  |_||___| |_| \_\\___/ |_| \_|")
        print(f"{Colour.RESET}")
        print(f"   >> 💥 {random.choice(HOMERUN_PHRASES)} 💥")
        
    elif contact_result.hit_type in ["1B", "2B", "3B"]:
        base = contact_result.hit_type
        print(f"   >> {Colour.GREEN}{base}! {random.choice(HIT_PHRASES)}{Colour.RESET}")
    else:
        print(f"   >> {contact_result.description}")

def announce_score_change(runs, batting_team_name):
    if runs > 0:
        print(f"   🚨 {Colour.gold}{runs} RUN(S) SCORED for {batting_team_name}!{Colour.RESET} 🚨")

def game_over(state, winner):
    print("\n" + "#"*60)
    print(f"{Colour.HEADER} GAME OVER {Colour.RESET}")
    
    away_name = getattr(state.away_team, 'name', 'Away')
    home_name = getattr(state.home_team, 'name', 'Home')
    winner_name = getattr(winner, 'name', 'Winner')
    
    print(f" Final Score: {away_name} {state.away_score} - {state.home_score} {home_name}")
    print(f" Winner: {Colour.gold}{winner_name}{Colour.RESET}")
    print("#"*60 + "\n")