import sqlite3

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Таблица для пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        code TEXT
    )
    ''')

    # Таблица для треков
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        track TEXT,
        delivery TEXT,
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    )
    ''')

    conn.commit()
    conn.close()


def add_user(user_id: int, code: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, code) VALUES (?, ?)", (user_id, code))
    conn.commit()
    conn.close()


def get_user_code(user_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def add_track(user_id: int, track: str, delivery: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tracks (user_id, track, delivery) VALUES (?, ?, ?)", (user_id, track, delivery))
    conn.commit()
    conn.close()


def get_tracks(user_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT track, delivery FROM tracks WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows
