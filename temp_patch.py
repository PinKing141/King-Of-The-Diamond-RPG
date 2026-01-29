import pathlib
import sys
path=pathlib.Path('database/populate_japan.py')
text=path.read_text()
start=text.find('def get_random_english_name')
if start==-1:
    sys.exit('not found func')
end=text.find('\n\n', start)
if end==-1:
    end=len(text)
new = '''def get_random_english_name(gender='M'):
    """Open a fresh connection per call to avoid cross-thread SQLite issues."""
    if not os.path.exists(NAME_DB_PATH):
        return "Yamada", "Taro"

    conn = None
    try:
        conn = sqlite3.connect(NAME_DB_PATH, check_same_thread=False)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT reading FROM last_names ORDER BY RANDOM() LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("SELECT kanji FROM names ORDER BY RANDOM() LIMIT 1")
        last_row = cursor.fetchone()
        last_reading = last_row[0] if last_row else "Yamada"

        try:
            sex_values = ["M", "m", "Male", "male", "MALE", "boy", "Boy", "BOY"]
            placeholders = "".join("?" * len(sex_values))
            cursor.execute(
                f"SELECT reading FROM first_names WHERE sex IN ({placeholders}) ORDER BY RANDOM() LIMIT 1",
                sex_values
            )
        except sqlite3.OperationalError:
            return "Yamada", "Taro"

        row = cursor.fetchone()
        first_reading = row[0] if row else "Taro"

        try:
            import pykakasi
            kks_local = pykakasi.kakasi()
            last_romaji = "".join([item['hepburn'] for item in kks_local.convert(last_reading)]).capitalize()
            first_romaji = "".join([item['hepburn'] for item in kks_local.convert(first_reading)]).capitalize()
            return last_romaji, first_romaji
        except Exception:
            return last_reading, first_reading

    except Exception:
        return "Yamada", "Taro"
    finally:
        if conn:
            conn.close()

'''
path.write_text(text[:start]+new+text[end:])
