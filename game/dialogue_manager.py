import json
import os
import random
from pathlib import Path
from typing import Dict, List

from ui.ui_display import Colour, clear_screen
from game.archetypes import archetype_persona_blurb

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "dialogues.json"


def _load_dialogues() -> Dict[str, dict]:
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as fh:
            entries = json.load(fh)
    except FileNotFoundError:
        return {}

    dialogue_map: Dict[str, dict] = {}
    for entry in entries:
        entry_id = entry.get("id")
        if entry_id:
            dialogue_map[entry_id] = entry
    return dialogue_map


DIALOGUE_DB = _load_dialogues()


def _coach_tone_lines(coach) -> List[str]:
    if not coach:
        return []
    drive = getattr(coach, 'drive', 50) or 50
    loyalty = getattr(coach, 'loyalty', 50) or 50
    volatility = getattr(coach, 'volatility', 50) or 50
    tone = []
    if drive >= 70:
        tone.append("His eyes stay on the scoreboard—results first, feelings later.")
    elif drive <= 35:
        tone.append("He focuses on growth over glory, urging patience.")
    if loyalty <= 40:
        tone.append("One misstep might cost you playing time; he makes that clear.")
    elif loyalty >= 70:
        tone.append("He reminds you the staff backs you as long as you fight for the team.")
    if volatility >= 65:
        tone.append("There's a sharp edge in his voice, like an ejection is one comment away.")
    elif volatility <= 35:
        tone.append("Even under pressure his tone stays even, inviting honest answers.")
    return tone

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
    speaker_label = data['speaker']
    coach = getattr(school, 'coach', None)
    if data['speaker'].lower() == 'coach' and coach:
        speaker_label = getattr(coach, 'name', data['speaker'])

    print(f"\n{Colour.CYAN}--- CONVERSATION: {speaker_label} ---{Colour.RESET}")
    print(f"\n\"{data['text']}\"\n")

    persona_line = archetype_persona_blurb(player)
    if persona_line:
        print(f"{Colour.MAGENTA}{persona_line}{Colour.RESET}")

    if data['speaker'].lower() == 'coach' and coach:
        for line in _coach_tone_lines(coach):
            print(f"{Colour.YELLOW}{line}{Colour.RESET}")
    
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