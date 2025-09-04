import os
from typing import List, Optional, Tuple
from datetime import datetime, timezone

DEV_MODE = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes", "dev")

if DEV_MODE:
    # Простой режим для разработки: все данные в памяти (исчезают при перезапуске)
    _users: dict[int, str] = {}
    # Дополнительные метаданные пользователей для DEV режима
    _user_meta: dict[int, dict] = {}
    _all_user_ids: set[int] = set()
    _tracks: list[dict] = []
    _track_photos: list[dict] = []
    _next_track_id: int = 1
    _recipients: dict[int, dict] = {}
    _shipments: list[dict] = []
    _next_shipment_id: int = 1
    _blocked_users: set[int] = set()

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

    def _ensure_user_row(user_id: int) -> None:
        # В DEV режиме просто регистрируем пользователя в наборе
        _all_user_ids.add(int(user_id))

    def _ensure_meta(user_id: int) -> dict:
        _ensure_user_row(user_id)
        meta = _user_meta.get(int(user_id))
        if not meta:
            meta = {
                "first_seen_at": None,
                "last_activity_at": None,
                "last_address_pressed_at": None,
                "last_sendcargo_pressed_at": None,
                "last_address_reminder_at": None,
                "last_sendcargo_reminder_at": None,
                "last_inactive_reminder_at": None,
            }
            _user_meta[int(user_id)] = meta
        return meta

    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

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
        _ensure_user_row(user_id)
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

    def get_user_id_by_code(code: str) -> Optional[int]:
        if not code:
            return None
        for uid, c in _users.items():
            if c == code:
                return uid
        return None

    def get_recipient(user_id: int) -> Optional[dict]:
        data = _recipients.get(user_id)
        if not data:
            return None
        # return shallow copy to avoid accidental external mutation
        return {"fio": data.get("fio", "").strip(), "phone": data.get("phone", "").strip(), "city": data.get("city", "").strip()}

    def set_recipient(user_id: int, fio: str, phone: str, city: str) -> None:
        _recipients[user_id] = {"fio": fio.strip(), "phone": phone.strip(), "city": city.strip()}

    def get_next_cargo_num(user_id: int) -> int:
        max_num = 0
        for s in _shipments:
            if s.get("user_id") == user_id:
                try:
                    n = int(s.get("cargo_num", 0))
                    if n > max_num:
                        max_num = n
                except Exception:
                    continue
        return max_num + 1

    def create_shipment(user_id: int, cargo_num: int, cargo_code: str, fio: str, phone: str, city: str, status: Optional[str] = None) -> int:
        global _next_shipment_id
        shipment = {
            "id": _next_shipment_id,
            "user_id": user_id,
            "cargo_num": int(cargo_num),
            "cargo_code": cargo_code,
            "fio": fio.strip(),
            "phone": phone.strip(),
            "city": city.strip(),
            "status": (status or None),
            "status_updated_at": (datetime.now(timezone.utc).isoformat() if status else None),
        }
        _shipments.append(shipment)
        _next_shipment_id += 1
        return shipment["id"]

    def get_user_id_by_cargo_code(cargo_code: str) -> Optional[int]:
        for s in _shipments:
            if s.get("cargo_code") == cargo_code:
                return int(s.get("user_id"))
        return None

    def update_shipment_status(cargo_code: str, status: str) -> None:
        for s in _shipments:
            if s.get("cargo_code") == cargo_code:
                s["status"] = status
                s["status_updated_at"] = datetime.now(timezone.utc).isoformat()
                return

    def list_user_shipments_by_status(user_id: int, status: str) -> List[str]:
        result: List[str] = []
        for s in _shipments:
            if int(s.get("user_id", 0)) == int(user_id) and (s.get("status") or "") == status:
                result.append(str(s.get("cargo_code")))
        return result

    def delete_all_user_shipments(user_id: int) -> int:
        before = len(_shipments)
        remaining = [s for s in _shipments if int(s.get("user_id", 0)) != int(user_id)]
        deleted = before - len(remaining)
        _shipments.clear()
        _shipments.extend(remaining)
        return deleted

    def count_user_shipments(user_id: int) -> int:
        return sum(1 for s in _shipments if int(s.get("user_id", 0)) == int(user_id))

    # --- Admin / moderation (DEV mode) ---
    def is_user_blocked(user_id: int) -> bool:
        return int(user_id) in _blocked_users

    def block_user(user_id: int, reason: Optional[str] = None) -> None:
        _blocked_users.add(int(user_id))

    def unblock_user(user_id: int) -> None:
        _blocked_users.discard(int(user_id))

    def delete_user_everything(user_id: int) -> dict:
        # Collect user's tracks to also remove photos
        user_id_int = int(user_id)
        user_tracks = [t[0] for t in get_tracks(user_id_int)]
        # Delete track photos for user's tracks
        before_photos = len(_track_photos)
        remaining_photos = [p for p in _track_photos if p.get("track") not in set(user_tracks)]
        deleted_photos = before_photos - len(remaining_photos)
        _track_photos.clear()
        _track_photos.extend(remaining_photos)

        # Delete tracks
        deleted_tracks = delete_all_user_tracks(user_id_int)

        # Delete shipments
        deleted_shipments = delete_all_user_shipments(user_id_int)

        # Delete recipient
        had_recipient = 1 if _recipients.pop(user_id_int, None) else 0

        # Delete user code and meta
        had_code = 1 if _users.pop(user_id_int, None) else 0
        _user_meta.pop(user_id_int, None)
        _all_user_ids.discard(user_id_int)

        # Remove from blocklist
        unblock_user(user_id_int)

        return {
            "deleted_tracks": int(deleted_tracks),
            "deleted_photos": int(deleted_photos),
            "deleted_shipments": int(deleted_shipments),
            "deleted_recipient": int(had_recipient),
            "deleted_user": int(had_code),
        }

    # --- Reminders & activity (DEV mode) ---
    def record_user_activity(user_id: int) -> None:
        meta = _ensure_meta(user_id)
        now = _now_iso()
        if not meta.get("first_seen_at"):
            meta["first_seen_at"] = now
        meta["last_activity_at"] = now

    def mark_pressed_address(user_id: int) -> None:
        meta = _ensure_meta(user_id)
        now = _now_iso()
        meta["last_address_pressed_at"] = now

    def mark_pressed_sendcargo(user_id: int) -> None:
        meta = _ensure_meta(user_id)
        now = _now_iso()
        meta["last_sendcargo_pressed_at"] = now

    def _older_than(ts_iso: Optional[str], days: int) -> bool:
        if not ts_iso:
            return False
        try:
            ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        except Exception:
            return False
        delta = datetime.now(timezone.utc) - ts
        return delta.total_seconds() >= days * 86400

    def get_users_for_address_reminder(days: int = 5) -> List[int]:
        result: List[int] = []
        for uid, meta in _user_meta.items():
            if meta.get("last_address_reminder_at"):
                continue
            if meta.get("last_address_pressed_at"):
                continue
            first_seen = meta.get("first_seen_at")
            if first_seen and _older_than(first_seen, days):
                result.append(int(uid))
        return result

    def get_users_for_sendcargo_reminder(days: int = 15) -> List[int]:
        result: List[int] = []
        for uid, meta in _user_meta.items():
            if meta.get("last_sendcargo_reminder_at"):
                continue
            if meta.get("last_sendcargo_pressed_at"):
                continue
            first_seen = meta.get("first_seen_at")
            if first_seen and _older_than(first_seen, days):
                result.append(int(uid))
        return result

    def get_users_for_inactive_reminder(days: int = 30) -> List[int]:
        result: List[int] = []
        for uid, meta in _user_meta.items():
            last_act = meta.get("last_activity_at")
            if not last_act:
                continue
            if not _older_than(last_act, days):
                continue
            last_sent = meta.get("last_inactive_reminder_at")
            # Отправляем один раз за период неактивности
            if last_sent and last_sent >= last_act:
                continue
            result.append(int(uid))
        return result

    def mark_address_reminder_sent(user_id: int) -> None:
        meta = _ensure_meta(user_id)
        meta["last_address_reminder_at"] = _now_iso()

    def mark_sendcargo_reminder_sent(user_id: int) -> None:
        meta = _ensure_meta(user_id)
        meta["last_sendcargo_reminder_at"] = _now_iso()

    def mark_inactive_reminder_sent(user_id: int) -> None:
        meta = _ensure_meta(user_id)
        meta["last_inactive_reminder_at"] = _now_iso()

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

    def _execute(query: str, params: Optional[tuple] = None) -> None:
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    if params is None:
                        cur.execute(query)
                    else:
                        cur.execute(query, params)
        finally:
            pool.putconn(conn)

    def _fetchone(query: str, params: Optional[tuple] = None) -> Optional[tuple]:
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    if params is None:
                        cur.execute(query)
                    else:
                        cur.execute(query, params)
                    return cur.fetchone()
        finally:
            pool.putconn(conn)

    def _fetchall(query: str, params: Optional[tuple] = None) -> List[tuple]:
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    if params is None:
                        cur.execute(query)
                    else:
                        cur.execute(query, params)
                    return cur.fetchall()
        finally:
            pool.putconn(conn)

    def init_db() -> None:
        _execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                code TEXT UNIQUE,
                first_seen_at TIMESTAMPTZ,
                last_activity_at TIMESTAMPTZ,
                last_address_pressed_at TIMESTAMPTZ,
                last_sendcargo_pressed_at TIMESTAMPTZ,
                last_address_reminder_at TIMESTAMPTZ,
                last_sendcargo_reminder_at TIMESTAMPTZ,
                last_inactive_reminder_at TIMESTAMPTZ
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
        _execute(
            """
            CREATE TABLE IF NOT EXISTS recipients (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                fio TEXT,
                phone TEXT,
                city TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        _execute(
            """
            CREATE TABLE IF NOT EXISTS shipments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                cargo_num INTEGER NOT NULL,
                cargo_code TEXT NOT NULL,
                fio TEXT,
                phone TEXT,
                city TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (user_id, cargo_num)
            )
            """
        )
        # Table for blocked users
        _execute(
            """
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id BIGINT PRIMARY KEY,
                banned_at TIMESTAMPTZ DEFAULT NOW(),
                reason TEXT
            )
            """
        )
        # Расширение схемы: добавляем статус отправки и дату обновления статуса
        _execute("ALTER TABLE shipments ADD COLUMN IF NOT EXISTS status TEXT")
        _execute("ALTER TABLE shipments ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMPTZ")
        # Расширение схемы пользователей: добавляем поля активности/напоминаний, если их нет
        _execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ")
        _execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ")
        _execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_address_pressed_at TIMESTAMPTZ")
        _execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_sendcargo_pressed_at TIMESTAMPTZ")
        _execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_address_reminder_at TIMESTAMPTZ")
        _execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_sendcargo_reminder_at TIMESTAMPTZ")
        _execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_inactive_reminder_at TIMESTAMPTZ")
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

    def get_user_id_by_code(code: str) -> Optional[int]:
        row = _fetchone("SELECT user_id FROM users WHERE code=%s", (code,))
        return row[0] if row else None

    def get_recipient(user_id: int) -> Optional[dict]:
        row = _fetchone("SELECT fio, phone, city FROM recipients WHERE user_id=%s", (user_id,))
        if not row:
            return None
        fio, phone, city = row
        return {"fio": (fio or "").strip(), "phone": (phone or "").strip(), "city": (city or "").strip()}

    def set_recipient(user_id: int, fio: str, phone: str, city: str) -> None:
        _execute(
            """
            INSERT INTO recipients (user_id, fio, phone, city, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET fio = EXCLUDED.fio,
                phone = EXCLUDED.phone,
                city = EXCLUDED.city,
                updated_at = NOW()
            """,
            (user_id, fio.strip(), phone.strip(), city.strip()),
        )

    def get_next_cargo_num(user_id: int) -> int:
        row = _fetchone("SELECT COALESCE(MAX(cargo_num), 0) + 1 FROM shipments WHERE user_id=%s", (user_id,))
        return int(row[0] if row and row[0] is not None else 1)

    def create_shipment(user_id: int, cargo_num: int, cargo_code: str, fio: str, phone: str, city: str, status: Optional[str] = None) -> int:
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO shipments (user_id, cargo_num, cargo_code, fio, phone, city, status, status_updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, CASE WHEN %s IS NULL THEN NULL ELSE NOW() END)
                        RETURNING id
                        """,
                        (user_id, int(cargo_num), cargo_code, fio.strip(), phone.strip(), city.strip(), status, status),
                    )
                    row = cur.fetchone()
                    return int(row[0])
        finally:
            pool.putconn(conn)

    def get_user_id_by_cargo_code(cargo_code: str) -> Optional[int]:
        row = _fetchone("SELECT user_id FROM shipments WHERE cargo_code=%s", (cargo_code,))
        return int(row[0]) if row and row[0] is not None else None

    def update_shipment_status(cargo_code: str, status: str) -> None:
        _execute(
            "UPDATE shipments SET status=%s, status_updated_at=NOW() WHERE cargo_code=%s",
            (status, cargo_code),
        )

    def list_user_shipments_by_status(user_id: int, status: str) -> List[str]:
        rows = _fetchall(
            "SELECT cargo_code FROM shipments WHERE user_id=%s AND status=%s ORDER BY id ASC",
            (user_id, status),
        )
        return [r[0] for r in rows]

    def delete_all_user_shipments(user_id: int) -> int:
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM shipments WHERE user_id=%s", (user_id,))
                    return cur.rowcount or 0
        finally:
            pool.putconn(conn)

    def count_user_shipments(user_id: int) -> int:
        row = _fetchone("SELECT COUNT(*) FROM shipments WHERE user_id=%s", (user_id,))
        return int(row[0]) if row and row[0] is not None else 0

    # --- Admin / moderation (PostgreSQL mode) ---
    def is_user_blocked(user_id: int) -> bool:
        row = _fetchone("SELECT 1 FROM blocked_users WHERE user_id=%s", (user_id,))
        return bool(row)

    def block_user(user_id: int, reason: Optional[str] = None) -> None:
        _execute(
            """
            INSERT INTO blocked_users (user_id, reason, banned_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET reason = EXCLUDED.reason,
                banned_at = NOW()
            """,
            (user_id, reason),
        )

    def unblock_user(user_id: int) -> None:
        _execute("DELETE FROM blocked_users WHERE user_id=%s", (user_id,))

    def delete_user_everything(user_id: int) -> dict:
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    # Count related records for reporting
                    cur.execute("SELECT COUNT(*) FROM tracks WHERE user_id=%s", (user_id,))
                    tracks_count = int(cur.fetchone()[0])
                    cur.execute("SELECT COUNT(*) FROM shipments WHERE user_id=%s", (user_id,))
                    shipments_count = int(cur.fetchone()[0])
                    cur.execute("SELECT COUNT(*) FROM recipients WHERE user_id=%s", (user_id,))
                    recipients_count = int(cur.fetchone()[0])

                    # Delete photos for user's tracks
                    cur.execute(
                        """
                        DELETE FROM track_photos
                        WHERE track IN (SELECT track FROM tracks WHERE user_id=%s)
                        """,
                        (user_id,)
                    )
                    deleted_photos = cur.rowcount or 0

                    # Remove from blocklist first
                    cur.execute("DELETE FROM blocked_users WHERE user_id=%s", (user_id,))

                    # Delete the user row (cascades to tracks/shipments/recipients)
                    cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
                    deleted_users = cur.rowcount or 0

                    return {
                        "deleted_tracks": int(tracks_count),
                        "deleted_photos": int(deleted_photos),
                        "deleted_shipments": int(shipments_count),
                        "deleted_recipient": int(recipients_count),
                        "deleted_user": int(deleted_users),
                    }
        finally:
            pool.putconn(conn)

    # --- Reminders & activity (PostgreSQL mode) ---
    def record_user_activity(user_id: int) -> None:
        _execute(
            """
            INSERT INTO users (user_id, first_seen_at, last_activity_at)
            VALUES (%s, NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET last_activity_at = NOW(),
                first_seen_at = COALESCE(users.first_seen_at, EXCLUDED.first_seen_at)
            """,
            (user_id,)
        )

    def mark_pressed_address(user_id: int) -> None:
        _execute(
            """
            INSERT INTO users (user_id, first_seen_at, last_activity_at, last_address_pressed_at)
            VALUES (%s, NOW(), NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET last_activity_at = NOW(),
                last_address_pressed_at = NOW(),
                first_seen_at = COALESCE(users.first_seen_at, EXCLUDED.first_seen_at)
            """,
            (user_id,)
        )

    def mark_pressed_sendcargo(user_id: int) -> None:
        _execute(
            """
            INSERT INTO users (user_id, first_seen_at, last_activity_at, last_sendcargo_pressed_at)
            VALUES (%s, NOW(), NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET last_activity_at = NOW(),
                last_sendcargo_pressed_at = NOW(),
                first_seen_at = COALESCE(users.first_seen_at, EXCLUDED.first_seen_at)
            """,
            (user_id,)
        )

    def get_users_for_address_reminder(days: int = 5) -> List[int]:
        rows = _fetchall(
            f"""
            SELECT user_id FROM users
            WHERE first_seen_at IS NOT NULL
              AND first_seen_at <= NOW() - INTERVAL '{int(days)} days'
              AND last_address_pressed_at IS NULL
              AND last_address_reminder_at IS NULL
            """
        )
        return [int(r[0]) for r in rows]

    def get_users_for_sendcargo_reminder(days: int = 15) -> List[int]:
        rows = _fetchall(
            f"""
            SELECT user_id FROM users
            WHERE first_seen_at IS NOT NULL
              AND first_seen_at <= NOW() - INTERVAL '{int(days)} days'
              AND last_sendcargo_pressed_at IS NULL
              AND last_sendcargo_reminder_at IS NULL
            """
        )
        return [int(r[0]) for r in rows]

    def get_users_for_inactive_reminder(days: int = 30) -> List[int]:
        rows = _fetchall(
            f"""
            SELECT user_id FROM users
            WHERE last_activity_at IS NOT NULL
              AND last_activity_at <= NOW() - INTERVAL '{int(days)} days'
              AND (
                    last_inactive_reminder_at IS NULL
                 OR last_inactive_reminder_at < last_activity_at
              )
            """
        )
        return [int(r[0]) for r in rows]

    def mark_address_reminder_sent(user_id: int) -> None:
        _execute("UPDATE users SET last_address_reminder_at=NOW() WHERE user_id=%s", (user_id,))

    def mark_sendcargo_reminder_sent(user_id: int) -> None:
        _execute("UPDATE users SET last_sendcargo_reminder_at=NOW() WHERE user_id=%s", (user_id,))

    def mark_inactive_reminder_sent(user_id: int) -> None:
        _execute("UPDATE users SET last_inactive_reminder_at=NOW() WHERE user_id=%s", (user_id,))
