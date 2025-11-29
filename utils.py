import sqlite3
import os

DB_PATH = os.path.join("Databases", "koshien.db")

def get_db_connection():
    """Establishes and returns a connection to the main game database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        return None

def fetch_player_status(conn):
    if PLAYER_ID is None:
        return None
    """Retrieves the main player's status and current date."""
    cursor = conn.cursor()
    
    # Query updated for new schema: first_name, last_name, players table, gamestate table
    query = """
        SELECT p.*, g.current_day, g.current_week, g.current_month, g.current_year
        FROM players p, gamestate g
        WHERE p.id = ? AND g.id = 1
    """
    cursor.execute(query, (PLAYER_ID,))
    row = cursor.fetchone()

    if row:
        data = dict(row)
        # Add a convenience 'name' field for display
        data['name'] = f"{data['first_name']} {data['last_name']}"
        return data
    return None

def update_game_state(conn, day, week, month, year):
    cursor = conn.cursor()
    cursor.execute("UPDATE gamestate SET current_day = ?, current_week = ?, current_month = ?, current_year = ? WHERE id = 1",
                   (day, week, month, year))
    conn.commit()

def increment_day(conn, current_state):
    day_map = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
    
    current_day_str = current_state['current_day']
    
    # Safety check if day is invalid
    if current_day_str not in day_map:
        current_day_str = 'MON'
        
    current_idx = day_map.index(current_day_str)
    
    next_idx = (current_idx + 1) % 7
    new_day = day_map[next_idx]
    
    new_week = current_state['current_week']
    new_month = current_state['current_month']
    new_year = current_state['current_year']

    if new_day == 'MON':
        new_week += 1
        if new_week > 4:
            new_week = 1
            new_month += 1
            if new_month > 12:
                new_month = 1
                new_year += 1

    update_game_state(conn, new_day, new_week, new_month, new_year)
    return new_day

PLAYER_ID = None

def set_player_id(pid):
    global PLAYER_ID
    PLAYER_ID = pid