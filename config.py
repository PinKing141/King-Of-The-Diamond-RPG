import os
import sys
import platform

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

if platform.system() == "Windows":
    USER_DATA_DIR = os.path.join(os.getenv('LOCALAPPDATA'), APP_NAME)
elif platform.system() == "Darwin": # macOS
    USER_DATA_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', APP_NAME)
else: # Linux/Unix
    USER_DATA_DIR = os.path.join(os.path.expanduser('~'), '.local', 'share', APP_NAME)

# Create the save directory if it doesn't exist
if not os.path.exists(USER_DATA_DIR):
    try:
        os.makedirs(USER_DATA_DIR)
        print(f"Created save directory: {USER_DATA_DIR}")
    except OSError:
        # Fallback to local folder if permission denied
        USER_DATA_DIR = os.path.join(os.getcwd(), "saves")
        if not os.path.exists(USER_DATA_DIR):
            os.makedirs(USER_DATA_DIR)

# The ACTIVE database file (the one currently being played)
DB_PATH = os.path.join(USER_DATA_DIR, "koshien_active.db")

# --- FILE PATHS ---
# Read-Only Assets
NAMES_DB_NAME = "names.sqlite"
CITIES_DB_NAME = "JP_Cities.db"
NAME_DB_PATH = os.path.join(DATA_FOLDER, NAMES_DB_NAME)
CITIES_DB_PATH = os.path.join(DATA_FOLDER, CITIES_DB_NAME)