import os
from typing import List, Optional, Tuple

import psycopg2
from psycopg2.pool import SimpleConnectionPool

# Railway Postgres плагин обычно создает переменную окружения DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (add Railway PostgreSQL plugin and redeploy)")

_pool: SimpleConnectionPool = None  # type: ignore


def _get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)
    return _pool


def _execute(query: str, params: tuple = ()) -> None:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
    finally:
        pool.putconn(conn)


def _fetchone(query: str, params: tuple = ()) -> Optional[tuple]:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()
    finally:
        pool.putconn(conn)


def _fetchall(query: str, params: tuple = ()) -> List[tuple]:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()
    finally:
        pool.putconn(conn)


def init_db() -> None:
    _execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            code TEXT UNIQUE
        )
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS tracks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            track TEXT NOT NULL,
            delivery TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


def get_user_code(user_id: int) -> Optional[str]:
    row = _fetchone("SELECT code FROM users WHERE user_id=%s", (user_id,))
    return row[0] if row else None


def _generate_next_code_tx(cur) -> str:
    # Берем все коды PB, находим максимальный номер и увеличиваем
    cur.execute("SELECT code FROM users WHERE code LIKE 'PB%'")
    rows = cur.fetchall()
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
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                # Блокируем строку пользователя (если есть) и генерим код атомарно
                cur.execute("SELECT code FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                row = cur.fetchone()
                if row and row[0]:
                    return row[0]

                new_code = _generate_next_code_tx(cur)
                cur.execute(
                    """
                    INSERT INTO users (user_id, code)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET code = EXCLUDED.code
                    """,
                    (user_id, new_code),
                )
                return new_code
    finally:
        pool.putconn(conn)


def add_track(user_id: int, track: str, delivery: str = "") -> None:
    _execute(
        "INSERT INTO tracks (user_id, track, delivery) VALUES (%s, %s, %s)",
        (user_id, track, delivery),
    )


def get_tracks(user_id: int) -> List[Tuple[str, Optional[str]]]:
    rows = _fetchall(
        "SELECT track, delivery FROM tracks WHERE user_id=%s ORDER BY id ASC",
        (user_id,),
    )
    return [(r[0], r[1]) for r in rows]
