import os
import shutil
import glob
from datetime import datetime
from config import USER_DATA_DIR, DB_PATH
from ui.ui_display import Colour, clear_screen

def get_save_slots():
    """
    Returns a list of dictionaries containing info about available save slots.
    """
    slots = []
    # Look for files named 'save_slot_*.db'
    pattern = os.path.join(USER_DATA_DIR, "save_slot_*.db")
    files = glob.glob(pattern)
    
    for f_path in files:
        filename = os.path.basename(f_path)
        # Extract slot number "save_slot_1.db" -> "1"
        try:
            slot_num = int(filename.replace("save_slot_", "").replace(".db", ""))
        except ValueError:
            continue
            
        # Get modification time
        mod_time = os.path.getmtime(f_path)
        date_str = datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M')
        
        slots.append({
            "slot": slot_num,
            "path": f_path,
            "date": date_str,
            "filename": filename
        })
    
    # Sort by slot number
    slots.sort(key=lambda x: x["slot"])
    return slots

def save_game(slot_num):
    """
    Copies the active DB to a save slot file.
    """
    if not os.path.exists(DB_PATH):
        return False, "No active game to save."
        
    target_path = os.path.join(USER_DATA_DIR, f"save_slot_{slot_num}.db")
    
    try:
        # Force close any connections? usually SQLite file copy works if WAL mode is okay
        # Ideally, ensure session is closed before calling this.
        shutil.copy2(DB_PATH, target_path)
        return True, f"Game saved to Slot {slot_num}."
    except Exception as e:
        return False, f"Error saving game: {e}"

def load_game(slot_num):
    """
    Copies a save slot file to the active DB path.
    """
    source_path = os.path.join(USER_DATA_DIR, f"save_slot_{slot_num}.db")
    
    if not os.path.exists(source_path):
        return False, "Save slot not found."
        
    try:
        # Overwrite active DB
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            
        shutil.copy2(source_path, DB_PATH)
        return True, f"Loaded Slot {slot_num}."
    except Exception as e:
        return False, f"Error loading save: {e}"

def delete_save(slot_num):
    target_path = os.path.join(USER_DATA_DIR, f"save_slot_{slot_num}.db")
    if os.path.exists(target_path):
        os.remove(target_path)
        return True, "Deleted."
    return False, "Not found."

def show_save_menu(mode="SAVE"):
    """
    Interactive menu for Saving/Loading.
    mode: "SAVE" or "LOAD"
    """
    while True:
        clear_screen()
        print(f"{Colour.HEADER}=== {mode} GAME ==={Colour.RESET}")
        
        slots = get_save_slots()
        existing_slots = {s['slot']: s for s in slots}
        
        # Display Slots 1-5 (or more)
        for i in range(1, 6):
            if i in existing_slots:
                info = existing_slots[i]
                print(f" {i}. Slot {i}  [{info['date']}]")
            else:
                print(f" {i}. Slot {i}  [Empty]")
                
        print(" 0. Back")
        
        choice = input("\nSelect Slot: ")
        if choice == '0': return False
        
        try:
            slot = int(choice)
            if 1 <= slot <= 5:
                if mode == "SAVE":
                    confirm = input(f"Overwrite Slot {slot}? (y/n): ") if slot in existing_slots else 'y'
                    if confirm.lower() == 'y':
                        success, msg = save_game(slot)
                        print(msg)
                        import time; time.sleep(1)
                        return True
                
                elif mode == "LOAD":
                    if slot not in existing_slots:
                        print("Slot is empty.")
                        import time; time.sleep(1)
                    else:
                        confirm = input(f"Load Slot {slot}? Unsaved progress will be lost. (y/n): ")
                        if confirm.lower() == 'y':
                            success, msg = load_game(slot)
                            print(msg)
                            import time; time.sleep(1)
                            return True
            else:
                print("Invalid slot.")
        except ValueError:
            pass