import os
import sqlite3
import importlib
import sys
import time
from types import SimpleNamespace

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import tempfile
import config

# Enable UI battle feedback for this run
os.environ["ADV_BATTLE_FEEDBACK"] = "1"

def backup_db(src_path: str, dst_path: str, *, retries: int = 5, delay: float = 1.0) -> str:
    """Create a read-only backup of the active DB with simple retry on locks."""

    last_err = None
    for _ in range(retries):
        try:
            src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True, timeout=5.0)
            dst = sqlite3.connect(dst_path, timeout=5.0)
            src.backup(dst)
            dst.close()
            src.close()
            return dst_path
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_err = exc
            time.sleep(delay)
    raise last_err

def main():
    fd, dst_path = tempfile.mkstemp(prefix="battle_feed_", suffix=".db")
    os.close(fd)

    # If the active DB is busy, fall back to a fresh temp DB.
    try:
        backup_db(config.DB_PATH, dst_path)
    except Exception:
        # Create a fresh schema on the temp DB to avoid locks.
        import database.setup_db as setup_db
        setup_db.DB_PATH = dst_path
        setup_db.engine.dispose()
        setup_db.engine = setup_db.create_engine(f"sqlite:///{dst_path}", connect_args={"timeout": 10})
        setup_db.SessionLocal.configure(bind=setup_db.engine)
        setup_db.create_database()

    # Point the config to the temp copy, then rebuild the DB layer using the new path.
    config.DB_PATH = dst_path
    import database.setup_db as setup_db
    importlib.reload(setup_db)

    # Force AI-driven choices so no interactive prompts trigger during the fast sim.
    import battery_system.battery_negotiation as battery_negotiation
    battery_negotiation._player_team_id = lambda _player: 2

    import match_engine.batter_logic as batter_logic
    batter_logic._player_team_id = lambda _player: 2
    batter_logic._user_controls_defense = lambda _state: False

    # Quick, DB-free render to prove the battle feed UI works even if the live DB is locked.
    from match_engine.scoreboard import Scoreboard
    from ui.ui_display import render_box_score_panel

    sc = Scoreboard()
    sc.innings = [(1, 0), (0, 2), (3, 1), (0, 0)]
    state = SimpleNamespace(
        away_team=SimpleNamespace(name="Date Tech High", id=2),
        home_team=SimpleNamespace(name="Chisaki Prep", id=1),
        error_summary=None,
        umpire_call_tilt={},
        logs=[
            "Battle math: bat control 72 vs difficulty 85 (contact mod -5). Drivers: velo 144, chase penalty -10",
            "Battle math: bat control 68 vs difficulty 62 (contact mod +10).",
            "Battle math: bat control 77 vs difficulty 70 (contact mod +5).",
        ],
    )
    render_box_score_panel(sc, state)

    try:
        os.remove(dst_path)
    except OSError:
        pass

if __name__ == "__main__":
    main()
