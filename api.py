import os
import hmac
import hashlib
import json
from urllib.parse import parse_qsl
from typing import Optional, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import (
    get_user_code,
    get_or_create_user_code,
    get_tracks,
    add_track,
    get_track_photos,
    delete_all_user_tracks,
    init_db,
)

try:
    from aiogram import Bot
except Exception:
    Bot = None  # type: ignore

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MANAGER_ID = int(os.getenv("MANAGER_ID", "0") or 0)
WAREHOUSE_ID = int(os.getenv("WAREHOUSE_ID", "0") or 0)

def _compute_webapp_secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()

def _verify_init_data(init_data: str, bot_token: str) -> Dict[str, Any]:
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing init_data")
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    provided_hash = params.pop("hash", None)
    if not provided_hash:
        raise HTTPException(status_code=401, detail="Missing hash")
    data_pairs = [f"{k}={params[k]}" for k in sorted(params.keys())]
    data_check_string = "\n".join(data_pairs)
    secret_key = _compute_webapp_secret_key(bot_token)
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if calc_hash != provided_hash:
        raise HTTPException(status_code=401, detail="Invalid init_data signature")
    user_raw = params.get("user")
    user: Dict[str, Any] = {}
    if user_raw:
        try:
            user = json.loads(user_raw)
        except Exception:
            user = {}
    return {"params": params, "user": user}

async def tg_user_dep(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, convert_underscores=True),
) -> Dict[str, Any]:
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not set")
    init_data = x_telegram_init_data or request.query_params.get("init_data") or request.query_params.get("initData")
    if not init_data and request.method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
            init_data = body.get("init_data") or body.get("initData")
        except Exception:
            pass
    verified = _verify_init_data(init_data or "", BOT_TOKEN)
    user = verified.get("user") or {}
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user in init_data")
    return user

class TrackRequest(BaseModel):
    track: str
    delivery: Optional[str] = None

class ManagerRequest(BaseModel):
    text: Optional[str] = None

app = FastAPI(title="Probuy API", version="0.1.0")

allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.get("/api/me")
async def me(user=Depends(tg_user_dep)):
    user_id = int(user["id"])
    code = get_user_code(user_id) or get_or_create_user_code(user_id)
    tracks = get_tracks(user_id)
    return {
        "user": {"id": user_id, "first_name": user.get("first_name"), "username": user.get("username")},
        "code": code,
        "tracks": [{"track": t, "delivery": d} for (t, d) in tracks],
    }

@app.post("/api/track")
async def add_track_ep(req: TrackRequest, user=Depends(tg_user_dep)):
    user_id = int(user["id"])
    track = (req.track or "").strip().upper()
    if len(track) < 8 or len(track) > 40 or not all(c.isalnum() and c.upper() == c for c in track):
        raise HTTPException(status_code=400, detail="Invalid track format")
    add_track(user_id, track, (req.delivery or "").strip())
    tracks = get_tracks(user_id)
    return {"ok": True, "tracks": [{"track": t, "delivery": d} for (t, d) in tracks]}

@app.delete("/api/tracks")
async def clear_tracks(user=Depends(tg_user_dep)):
    user_id = int(user["id"])
    deleted = delete_all_user_tracks(user_id)
    return {"ok": True, "deleted": deleted}

@app.get("/api/track/{track}/photos")
async def get_photos(track: str, user=Depends(tg_user_dep)):
    _ = user
    t = (track or "").strip().upper()
    photos = get_track_photos(t)
    return {"track": t, "photos": photos}

@app.post("/api/manager")
async def notify_manager(req: ManagerRequest, user=Depends(tg_user_dep)):
    if not MANAGER_ID:
        return {"ok": True, "sent": False}
    if not BOT_TOKEN or Bot is None:
        raise HTTPException(status_code=500, detail="Bot not available for notifications")
    bot = Bot(token=BOT_TOKEN)
    try:
        full_name = f"{user.get('first_name','')} {user.get('last_name','')}".strip()
        username = f"@{user.get('username')}" if user.get('username') else "не указан"
        text = (
            "📞 <b>КЛИЕНТ ХОЧЕТ СВЯЗАТЬСЯ С МЕНЕДЖЕРОМ (из Mini App)</b>\n\n"
            f"👤 Имя: {full_name}\n"
            f"📱 Username: {username}\n"
            f"🆔 Telegram ID: <code>{user.get('id')}</code>\n\n"
            f"📝 Сообщение: {req.text or '—'}"
        )
        await bot.send_message(MANAGER_ID, text, parse_mode="HTML")
    finally:
        await bot.session.close()
    return {"ok": True, "sent": True}

@app.on_event("startup")
async def _startup():
    try:
        init_db()
    except Exception:
        pass

_dist_dir = os.path.join(os.path.dirname(__file__), "web", "dist")
if os.path.isdir(_dist_dir):
    app.mount("/", StaticFiles(directory=_dist_dir, html=True), name="static")
