import os
import sys
import platform

from core.paths import active_db_path, get_app_paths

def get_base_path():
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    """
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.abspath(__file__))

# --- DIRECTORY CONFIGURATION ---
BASE_DIR = get_base_path()

# Data folder for READ-ONLY assets (bundled in EXE)
DATA_DIR_NAME = "data"
DATA_FOLDER = os.path.join(BASE_DIR, DATA_DIR_NAME)

# Ensure the data folder exists (Dev mode only)
if not os.path.exists(DATA_FOLDER) and not getattr(sys, 'frozen', False):
    try:
        os.makedirs(DATA_FOLDER)
        print(f"Created data directory: {DATA_FOLDER}")
    except OSError as e:
        print(f"Error creating data directory: {e}")

# --- USER DATA (SAVE FILES) ---
# Determine standard user data directory based on OS
APP_NAME = "Koshien_RPG"

_APP_PATHS = get_app_paths()
USER_DATA_DIR = str(_APP_PATHS.saves_dir)

# The ACTIVE database file (the one currently being played)
DB_PATH = str(active_db_path())

# --- FILE PATHS ---
# Read-Only Assets
NAMES_DB_NAME = "names.sqlite"
CITIES_DB_NAME = "JP_Cities.db"
NAME_DB_PATH = os.path.join(DATA_FOLDER, NAMES_DB_NAME)
CITIES_DB_PATH = os.path.join(DATA_FOLDER, CITIES_DB_NAME)