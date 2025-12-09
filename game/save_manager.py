import json
import os
import glob
import sqlite3
import logging
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from config import USER_DATA_DIR, DB_PATH
from ui.ui_display import Colour, clear_screen
from database.setup_db import (
    close_all_sessions,
    create_database,
    get_session,
    GameState,
)
from core.exceptions import SaveCorruptError, SaveError, SaveNotFoundError
from core.io_interface import IOInterface


LOGGER = logging.getLogger(__name__)


def _backup_database(source_path, target_path):
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source database not found: {source_path}")

    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    src = sqlite3.connect(source_path)
    dst = sqlite3.connect(target_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _rebind_db_engine():
    """Point SQLAlchemy's engine/session to the current DB_PATH (test-friendly)."""
    import database.setup_db as setup_db

    try:
        setup_db.engine.dispose()
    except SQLAlchemyError as exc:
        LOGGER.warning("Engine dispose failed during rebind: %s", exc)

    setup_db.engine = create_engine(f"sqlite:///{DB_PATH}")
    setup_db.SessionLocal.configure(bind=setup_db.engine)


def _gamestate_present():
    """Lightweight existence check that tolerates partial schemas in tests."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT COUNT(*) FROM gamestate").fetchone()
        return bool(row and row[0])
    except sqlite3.OperationalError:
        return False
    finally:
        if conn:
            conn.close()


def _safe_json_load(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _read_gamestate_metadata(db_path):
    if not os.path.exists(db_path):
        return {}
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT current_week, current_month, current_year, last_error_summary, last_coach_order_result, last_telemetry_blob FROM gamestate LIMIT 1"
        ).fetchone()
        if not row:
            return {}
        return {
            "current_week": row["current_week"],
            "current_month": row["current_month"],
            "current_year": row["current_year"],
            "last_error_summary": _safe_json_load(row["last_error_summary"]),
            "last_coach_order_result": _safe_json_load(row["last_coach_order_result"]),
            "last_telemetry_blob": _safe_json_load(row["last_telemetry_blob"]),
        }
    except sqlite3.OperationalError:
        return {}
    finally:
        if conn is not None:
            conn.close()


def _format_slot_preview(meta):
    if not meta:
        return ""
    parts = []
    week = meta.get("current_week")
    year = meta.get("current_year")
    if week:
        label = f"Week {week}"
        if year:
            label += f" / Year {year}"
        parts.append(label)
    order = meta.get("last_coach_order_result") or {}
    if order:
        order_info = order.get("order") or {}
        name = order_info.get("description") or order_info.get("key")
        progress = order.get("progress") or {}
        if name:
            status = "DONE" if order.get("completed") else f"{progress.get('value', 0)}/{progress.get('target', 0)}"
            reward = order.get("reward_delta") or {}
            reward_bits = []
            if reward.get("trust"):
                reward_bits.append(f"Trust+{reward['trust']}")
            if reward.get("ability_points"):
                reward_bits.append(f"AP+{reward['ability_points']}")
            reward_text = f" [{', '.join(reward_bits)}]" if reward_bits else ""
            parts.append(f"Coach Order: {status} - {name}{reward_text}")
    errors = meta.get("last_error_summary") or {}
    if errors:
        home_errors = len(errors.get("home", []) or [])
        away_errors = len(errors.get("away", []) or [])
        parts.append(f"Errors H:{home_errors} / A:{away_errors}")
    return " | ".join(parts)

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
        
        metadata = _read_gamestate_metadata(f_path)
        slots.append({
            "slot": slot_num,
            "path": f_path,
            "date": date_str,
            "filename": filename,
            "metadata": metadata,
            "preview": _format_slot_preview(metadata),
        })
    
    # Sort by slot number
    slots.sort(key=lambda x: x["slot"])
    return slots


AUTOSAVE_PATH = os.path.join(USER_DATA_DIR, "autosave_match.db")
AUTOSAVE_META = os.path.join(USER_DATA_DIR, "autosave_match_meta.json")


def autosave_match_state(*, state=None, reason: str = "mid-match") -> None:
    """Lightweight autosave to discourage reload abuse during key match moments."""

    if not os.path.exists(DB_PATH):
        return
    meta = {
        "reason": reason,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    if state is not None:
        meta.update(
            {
                "inning": getattr(state, "inning", None),
                "half": getattr(state, "top_bottom", None),
                "outs": getattr(state, "outs", None),
                "home_score": getattr(state, "home_score", None),
                "away_score": getattr(state, "away_score", None),
            }
        )

    try:
        _backup_database(DB_PATH, AUTOSAVE_PATH)
        with open(AUTOSAVE_META, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except (sqlite3.Error, OSError) as exc:
        print(f"Autosave skipped: {exc}")
        return

def save_game(slot_num):
    """Snapshot the active database into the requested save slot."""
    if not os.path.exists(DB_PATH):
        raise SaveError("No active game database found to save.")

    target_path = os.path.join(USER_DATA_DIR, f"save_slot_{slot_num}.db")

    try:
        close_all_sessions()
        _backup_database(DB_PATH, target_path)
        return True, f"Game saved to Slot {slot_num}."
    except sqlite3.Error as exc:
        raise SaveError(f"Database error during save: {exc}")
    except OSError as exc:
        raise SaveError(f"Disk error during save: {exc}")

def load_game(slot_num):
    """Restore the active database from a save slot, verifying GameState afterward."""
    source_path = os.path.join(USER_DATA_DIR, f"save_slot_{slot_num}.db")

    if not os.path.exists(source_path):
        return False, f"Save slot {slot_num} not found."

    try:
        close_all_sessions()
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)

        _backup_database(source_path, DB_PATH)
        _rebind_db_engine()
        create_database()  # ensures schema + GameState row

        if not _gamestate_present():
            raise SaveCorruptError("Save file loaded, but GameState table is missing or empty.")

        return True, f"Loaded Slot {slot_num}."
    except sqlite3.DatabaseError as exc:
        return False, f"Save file is not a valid database: {exc}"
    except (SaveCorruptError, SaveError) as exc:
        return False, str(exc)
    except OSError as exc:
        return False, f"System error loading save: {exc}"

def delete_save(slot_num):
    target_path = os.path.join(USER_DATA_DIR, f"save_slot_{slot_num}.db")
    if os.path.exists(target_path):
        os.remove(target_path)
        return True, "Deleted."
    return False, "Not found."


def delete_autosave():
    """Removes the temporary match resume data."""
    deleted = False
    if os.path.exists(AUTOSAVE_PATH):
        try:
            os.remove(AUTOSAVE_PATH)
            deleted = True
        except OSError:
            pass

    if os.path.exists(AUTOSAVE_META):
        try:
            os.remove(AUTOSAVE_META)
        except OSError:
            pass

    return deleted

def show_save_menu(mode="SAVE", *, io: Optional[IOInterface] = None):
    """
    Interactive menu for Saving/Loading.
    mode: "SAVE" or "LOAD"
    """
    log = io.log if io else print
    prompt_fn = io.prompt if io else input
    clear_fn = io.clear if io else clear_screen
    wait_fn = io.wait if io else (lambda s: __import__("time").sleep(s))

    while True:
        clear_fn()
        log(f"{Colour.HEADER}=== {mode} GAME ==={Colour.RESET}")
        
        slots = get_save_slots()
        existing_slots = {s['slot']: s for s in slots}
        
        # Display Slots 1-5 (or more)
        for i in range(1, 6):
            if i in existing_slots:
                info = existing_slots[i]
                log(f" {i}. Slot {i}  [{info['date']}]")
                preview = info.get("preview") or _format_slot_preview(info.get("metadata"))
                if preview:
                    log(f"    {preview}")
            else:
                log(f" {i}. Slot {i}  [Empty]")
                
        log(" 0. Back")
        log(" 9. Clear Autosave")
        
        choice = prompt_fn("\nSelect Slot: ")
        if choice == '0':
            return False

        if choice == '9':
            if delete_autosave():
                log(f"{Colour.GREEN}Autosave cleared.{Colour.RESET}")
            else:
                log("No autosave found.")
            wait_fn(1)
            continue
        
        try:
            slot = int(choice)
            if 1 <= slot <= 5:
                if mode == "SAVE":
                    confirm = prompt_fn(f"Overwrite Slot {slot}? (y/n): ") if slot in existing_slots else 'y'
                    if confirm.lower() == 'y':
                        try:
                            success, msg = save_game(slot)
                            log(f"{Colour.GREEN}{msg}{Colour.RESET}")
                        except SaveError as exc:
                            log(f"{Colour.FAIL}Save Failed: {exc}{Colour.RESET}", level="error")
                        wait_fn(1)
                        return True
                
                elif mode == "LOAD":
                    if slot not in existing_slots:
                        log("Slot is empty.")
                        wait_fn(1)
                    else:
                        confirm = prompt_fn(f"Load Slot {slot}? Unsaved progress will be lost. (y/n): ")
                        if confirm.lower() == 'y':
                            try:
                                success, msg = load_game(slot)
                                log(f"{Colour.GREEN}{msg}{Colour.RESET}")
                            except SaveCorruptError as exc:
                                log(f"{Colour.FAIL}CORRUPT SAVE: {exc}{Colour.RESET}", level="error")
                            except SaveNotFoundError as exc:
                                log(f"{Colour.WARNING}{exc}{Colour.RESET}", level="warning")
                            except SaveError as exc:
                                log(f"{Colour.FAIL}Load Error: {exc}{Colour.RESET}", level="error")
                            wait_fn(1)
                            return True
            else:
                log("Invalid slot.", level="warning")
        except ValueError:
            pass