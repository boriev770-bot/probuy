import os
import sqlite3
from typing import List, Optional, Tuple

# Путь к БД. Для Railway Volume укажи переменную окружения DB_PATH, например: /app/data/database.db
DB_PATH = os.getenv("DB_PATH", "database.db")


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            code TEXT UNIQUE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            track TEXT,
            delivery TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """
    )

    conn.commit()
    conn.close()


def get_user_code(user_id: int) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def _generate_next_code(cursor) -> str:
    cursor.execute("SELECT code FROM users WHERE code LIKE 'PB%'")
    rows = cursor.fetchall()
    max_num = 0
    for (code,) in rows:
        try:
            if code and code.startswith("PB"):
                num = int(code[2:])
                if num > max_num:
                    max_num = num
        except Exception:
            continue
    next_num = max_num + 1
    return f"PB{next_num:05d}"


def get_or_create_user_code(user_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.execute("SELECT code FROM users WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        if row and row[0]:
            code = row[0]
        else:
            code = _generate_next_code(cursor)
            cursor.execute(
                "INSERT OR REPLACE INTO users (user_id, code) VALUES (?, ?)",
                (user_id, code),
            )
        conn.commit()
        return code
    finally:
        conn.close()


def add_track(user_id: int, track: str, delivery: str = "") -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tracks (user_id, track, delivery) VALUES (?, ?, ?)",
        (user_id, track, delivery),
    )
    conn.commit()
    conn.close()


def get_tracks(user_id: int) -> List[Tuple[str, Optional[str]]]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT track, delivery FROM tracks WHERE user_id=? ORDER BY id ASC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows
