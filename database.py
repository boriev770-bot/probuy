import os
from typing import List, Optional, Tuple

DEV_MODE = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes", "dev")

if DEV_MODE:
    # Простой режим для разработки: все данные в памяти (исчезают при перезапуске)
    _users: dict[int, str] = {}
    _tracks: list[dict] = []
    _track_photos: list[dict] = []
    _next_track_id: int = 1

    def init_db() -> None:
        # Миграция кодов в новый формат EM03-xxxxx
        global _users
        if not _users:
            return
        migrated: dict[int, str] = {}
        for uid, code in list(_users.items()):
            if not code:
                continue
            if code.startswith("EM03-"):
                migrated[uid] = code
                continue
            # PBxxxxx -> EM03-xxxxx
            if code.startswith("PB") and len(code) >= 7 and code[2:].isdigit():
                migrated[uid] = f"EM03-{int(code[2:]):05d}"
                continue
            # Попробуем извлечь числовую часть и нормализовать
            digits = "".join(ch for ch in code if ch.isdigit())
            if digits:
                migrated[uid] = f"EM03-{int(digits):05d}"
            else:
                migrated[uid] = code
        if migrated:
            _users.clear()
            _users.update(migrated)

    def _generate_next_code() -> str:
        max_num = 0
        for code in _users.values():
            try:
                if code and code.startswith("EM03-"):
                    num = int(code.split("-", 1)[1])
                    if num > max_num:
                        max_num = num
            except Exception:
                continue
        return f"EM03-{max_num + 1:05d}"

    def get_user_code(user_id: int) -> Optional[str]:
        return _users.get(user_id)

    def get_or_create_user_code(user_id: int) -> str:
        code = _users.get(user_id)
        if code:
            return code
        code = _generate_next_code()
        _users[user_id] = code
        return code

    def add_track(user_id: int, track: str, delivery: str = "") -> None:
        global _next_track_id
        _tracks.append({
            "id": _next_track_id,
            "user_id": user_id,
            "track": track,
            "delivery": delivery,
        })
        _next_track_id += 1

    def get_tracks(user_id: int) -> List[Tuple[str, Optional[str]]]:
        rows = [t for t in _tracks if t["user_id"] == user_id]
        rows.sort(key=lambda t: t["id"])  # по аналогии с ORDER BY id ASC
        return [(t["track"], t.get("delivery")) for t in rows]

    def add_track_photo(track: str, file_id: str, uploaded_by: Optional[int] = None, caption: Optional[str] = None) -> None:
        _track_photos.append({
            "track": track,
            "file_id": file_id,
            "uploaded_by": uploaded_by,
            "caption": caption,
        })

    def get_track_photos(track: str) -> List[str]:
        rows = [p for p in _track_photos if p["track"] == track]
        return [p["file_id"] for p in rows]

    def find_user_ids_by_track(track: str) -> List[int]:
        return sorted(list({t["user_id"] for t in _tracks if t["track"] == track}))

    def delete_all_user_tracks(user_id: int) -> int:
        before = len(_tracks)
        remaining = [t for t in _tracks if t["user_id"] != user_id]
        deleted = before - len(remaining)
        _tracks.clear()
        _tracks.extend(remaining)
        return deleted

else:
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
        _execute(
            """
            CREATE TABLE IF NOT EXISTS track_photos (
                id SERIAL PRIMARY KEY,
                track TEXT NOT NULL,
                file_id TEXT NOT NULL,
                uploaded_by BIGINT,
                caption TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        # Миграция: PBxxxxx -> EM03-xxxxx
        _execute(
            """
            UPDATE users
            SET code = 'EM03-' || LPAD(REGEXP_REPLACE(code, '\\D', '', 'g'), 5, '0')
            WHERE code IS NOT NULL
              AND code NOT LIKE 'EM03-%'
              AND REGEXP_REPLACE(code, '\\D', '', 'g') <> ''
            """
        )

    def get_user_code(user_id: int) -> Optional[str]:
        row = _fetchone("SELECT code FROM users WHERE user_id=%s", (user_id,))
        return row[0] if row else None

    def _generate_next_code_tx(cur) -> str:
        # Берем все коды EM03-xxxxx, находим максимальный номер и увеличиваем
        cur.execute("SELECT code FROM users WHERE code LIKE 'EM03-%'")
        rows = cur.fetchall()
        max_num = 0
        for (code,) in rows:
            try:
                if code and code.startswith("EM03-"):
                    num = int(code.split('-', 1)[1])
                    if num > max_num:
                        max_num = num
            except Exception:
                continue
        next_num = max_num + 1
        return f"EM03-{next_num:05d}"

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

    def add_track_photo(track: str, file_id: str, uploaded_by: Optional[int] = None, caption: Optional[str] = None) -> None:
        _execute(
            "INSERT INTO track_photos (track, file_id, uploaded_by, caption) VALUES (%s, %s, %s, %s)",
            (track, file_id, uploaded_by, caption),
        )

    def get_track_photos(track: str) -> List[str]:
        rows = _fetchall(
            "SELECT file_id FROM track_photos WHERE track=%s ORDER BY id ASC",
            (track,),
        )
        return [r[0] for r in rows]

    def find_user_ids_by_track(track: str) -> List[int]:
        rows = _fetchall(
            "SELECT DISTINCT user_id FROM tracks WHERE track=%s",
            (track,),
        )
        return [r[0] for r in rows if r and r[0] is not None]

    def delete_all_user_tracks(user_id: int) -> int:
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM tracks WHERE user_id=%s", (user_id,))
                    return cur.rowcount or 0
        finally:
            pool.putconn(conn)
