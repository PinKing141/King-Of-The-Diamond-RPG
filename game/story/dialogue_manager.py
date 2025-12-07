import json
import os
import random
from pathlib import Path
from typing import Dict, List

from ui.ui_display import Colour, clear_screen
from game.personnel.archetypes import archetype_persona_blurb

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "dialogues.json"
PERSONA_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "coach_personality_dialogues.json"


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


def _load_persona_dialogues() -> Dict[str, Dict[str, str]]:
    try:
        with open(PERSONA_DATA_PATH, "r", encoding="utf-8") as fh:
            entries = json.load(fh)
    except FileNotFoundError:
        return {}

    persona_map: Dict[str, Dict[str, str]] = {}
    for entry in entries:
        event_id = entry.get("id")
        persona = entry.get("personality")
        text = entry.get("text")
        if not event_id or not persona or not text:
            continue
        persona_map.setdefault(event_id, {})[persona] = text
    return persona_map


PERSONA_DIALOGUE_DB = _load_persona_dialogues()


def _persona_flavor_lines(coach) -> List[str]:
    """Add subtle tonal shifts based on persona + sliders."""
    if not coach:
        return []
    persona = getattr(coach, 'personality', '') or ''
    drive = getattr(coach, 'drive', 50) or 50
    loyalty = getattr(coach, 'loyalty', 50) or 50
    volatility = getattr(coach, 'volatility', 50) or 50
    logic = getattr(coach, 'logic', 0.5) or 0.5
    tradition = getattr(coach, 'tradition', 0.5) or 0.5

    lines: List[str] = []
    if persona == "Gruff":
        if loyalty >= 70:
            lines.append("His tone softens when he talks about protecting his players.")
        else:
            lines.append("He growls that mistakes earn a seat on the bench.")
    elif persona == "Strict":
        if volatility >= 65:
            lines.append("Rules feel like knives—break one and you'll know it.")
        else:
            lines.append("He recites expectations like a creed, calm but absolute.")
    elif persona == "Passionate":
        if drive >= 70:
            lines.append("His fire is contagious; the room vibrates with energy.")
        else:
            lines.append("Even his jokes crackle—he refuses to let focus dip.")
    elif persona == "Logical":
        if logic >= 0.7:
            lines.append("He references probabilities more than feelings.")
        else:
            lines.append("He still trusts the numbers, but leaves room for gut calls.")
    elif persona == "Stoic":
        if volatility <= 35:
            lines.append("No wasted words; silence does the heavy lifting.")
        else:
            lines.append("He keeps still, but the tension in his jaw says plenty.")
    elif persona == "Maverick":
        if tradition <= 0.35:
            lines.append("He hints at a trick no one sees coming.")
        else:
            lines.append("He'll break tradition—but only when the stakes demand it.")
    elif persona == "Mentorly":
        if loyalty >= 70:
            lines.append("He frames every demand as an investment in you.")
        else:
            lines.append("He teaches, but expects you to earn every lesson.")
    elif persona == "Philosophical":
        if volatility <= 35:
            lines.append("He speaks in calm riddles that somehow steady the room.")
        else:
            lines.append("His metaphors wander, but they always land on effort and grit.")

    return lines


def _persona_text_variant(coach) -> str | None:
    """Return a brief suffix that nudges tone within the same persona using sliders."""
    if not coach:
        return None
    persona = getattr(coach, 'personality', '') or ''
    drive = getattr(coach, 'drive', 50) or 50
    loyalty = getattr(coach, 'loyalty', 50) or 50
    volatility = getattr(coach, 'volatility', 50) or 50

    if persona == "Gruff" and loyalty >= 70:
        return "He taps the desk once, like a quiet promise to back you up."
    if persona == "Gruff" and loyalty < 50:
        return "His stare says playing time is earned, not gifted."
    if persona == "Passionate" and drive >= 70:
        return "His knuckles whiten from clenching the lineup card."
    if persona == "Passionate" and volatility >= 65:
        return "You can almost feel the room heat up around him."
    if persona == "Logical" and loyalty <= 45:
        return "He quotes matchups like equations—no sentimental starts."
    if persona == "Logical" and drive <= 55:
        return "He nudges you toward the data, not the spotlight."
    if persona == "Stoic" and volatility <= 35:
        return "The silence is steadying; you match his calm."
    if persona == "Stoic" and loyalty >= 65:
        return "He gives a rare nod; trust earned quietly."
    if persona == "Maverick" and volatility >= 65:
        return "There's mischief in his pause—some trick is coming."
    if persona == "Mentorly" and loyalty >= 70:
        return "He frames it as a lesson tailored just for you."
    if persona == "Philosophical" and drive >= 65:
        return "His metaphor somehow lands on grit and sweat."
    return None


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

    coach = getattr(school, 'coach', None)
    persona_text = None
    if coach:
        persona = getattr(coach, 'personality', 'Stoic')
        persona_text = PERSONA_DIALOGUE_DB.get(event_id, {}).get(persona)

    active_text = persona_text or data['text']
    if coach:
        active_text = active_text.replace("{name}", getattr(coach, "name", "Coach"))
        variant = _persona_text_variant(coach)
        if variant:
            active_text = f"{active_text} {variant}"
    print(f"\n\"{active_text}\"\n")

    persona_line = archetype_persona_blurb(player)
    if persona_line:
        print(f"{Colour.MAGENTA}{persona_line}{Colour.RESET}")

    if data['speaker'].lower() == 'coach' and coach:
        for line in _coach_tone_lines(coach):
            print(f"{Colour.YELLOW}{line}{Colour.RESET}")
        for line in _persona_flavor_lines(coach):
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