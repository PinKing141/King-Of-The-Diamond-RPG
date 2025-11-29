import json
import os
import random
from ui.ui_display import Colour, clear_screen

# Example Database of Dialogues (Ideally this would be a JSON file)
# Structure: Event ID -> List of possible dialogue branches
DIALOGUE_DB = {
    "coach_meeting_strategy": {
        "speaker": "Coach",
        "text": "We have a tough match coming up. I need you focused. What's your mindset?",
        "options": [
            {
                "text": "I'll strike everyone out.",
                "effects": {"morale": 5, "coach_trust": 2},
                "response": "Good energy. Keep that fire."
            },
            {
                "text": "I'll follow your lead, Coach.",
                "effects": {"coach_trust": 5, "morale": 0},
                "response": "That's what I like to hear. Discipline wins games."
            },
            {
                "text": "Honestly? I'm terrified.",
                "effects": {"morale": -5, "coach_trust": -2},
                "response": "Fear is natural. Use it. Don't let it control you."
            }
        ]
    },
    "teammate_practice_extra": {
        "speaker": "Teammate",
        "text": "Hey! A few of us are staying late for batting practice. Want to join?",
        "options": [
            {
                "text": "Yeah, let's grind!",
                "effects": {"stamina": -5, "contact": 0.5, "friendship": 5},
                "response": "Awesome! Let's get to work."
            },
            {
                "text": "Sorry, I need to rest.",
                "effects": {"stamina": 5, "friendship": -2},
                "response": "Ah, okay. Rest up for the game."
            }
        ]
    }
}

def run_dialogue_event(event_id, player, school):
    """
    Runs a dialogue interaction in the console.
    Returns a summary string of the outcome.
    """
    if event_id not in DIALOGUE_DB:
        return f"Error: Dialogue '{event_id}' not found."
    
    data = DIALOGUE_DB[event_id]
    
    # 1. Display Interface (Godot would render a textbox here)
    clear_screen()
    print(f"\n{Colour.CYAN}--- CONVERSATION: {data['speaker']} ---{Colour.RESET}")
    print(f"\n\"{data['text']}\"\n")
    
    # 2. Display Options
    for i, opt in enumerate(data['options']):
        print(f" {i+1}. {opt['text']}")
        
    # 3. Get Input
    while True:
        try:
            choice = int(input("\nSelect: ")) - 1
            if 0 <= choice < len(data['options']):
                break
        except ValueError:
            pass
        print("Invalid choice.")
        
    selected_opt = data['options'][choice]
    
    # 4. Apply Effects
    effects_summary = []
    for stat, val in selected_opt.get("effects", {}).items():
        # Handle Player Stats
        if hasattr(player, stat):
            curr = getattr(player, stat)
            setattr(player, stat, curr + val)
            sign = "+" if val > 0 else ""
            effects_summary.append(f"{stat.title()} {sign}{val}")
        
        # Handle Special Stats (Friendship, Coach Trust) - these might need a dedicated dict on Player
        # For now, we simulate it or print it.
        elif stat == "coach_trust":
            # Assuming we might add this field later or store it in a relationship table
            effects_summary.append(f"Coach Trust {sign}{val}")
        elif stat == "friendship":
            effects_summary.append(f"Teammate Bond {sign}{val}")

    # 5. Show Response
    print(f"\n{data['speaker']}: \"{selected_opt['response']}\"")
    print(f"{Colour.YELLOW}Result: {', '.join(effects_summary)}{Colour.RESET}")
    
    input("[Press Enter]")
    return f"Dialogue Complete: {data['speaker']}"

# --- API FOR GODOT (Future Proofing) ---
def get_dialogue_json(event_id):
    """
    Returns the raw dictionary for Godot to parse.
    Godot will call this, render the buttons, and send back the choice index.
    """
    return DIALOGUE_DB.get(event_id)

def process_dialogue_choice(event_id, choice_index, player):
    """
    Godot sends the choice index here to apply effects.
    """
    data = DIALOGUE_DB.get(event_id)
    if not data: return {"error": "Invalid ID"}
    
    selected_opt = data['options'][choice_index]
    # ... (Apply logic identical to run_dialogue_event above) ...
    return selected_opt['response']