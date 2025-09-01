import os
import hmac
import hashlib
import json
from urllib.parse import parse_qsl
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

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
DEV_MODE = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes", "dev")

# Текст адреса склада: вставлен ровно как указано пользователем
CHINA_WAREHOUSE_ADDRESS = (
    "张生生{client_code}\n"
    "16604524466 \n"
    "广东省 佛山市 南海区 里水镇 东秀路 河塱沙5号 一楼仓库EM00-ХХХХХ"
)

DELIVERY_TYPES: Dict[str, Dict[str, str]] = {
    "fast_auto": {"name": "\ud83d\ude9b \u0411\u044b\u0441\u0442\u0440\u043e\u0435 \u0430\u0432\u0442\u043e"},
    "slow_auto": {"name": "\ud83d\ude9a \u041c\u0435\u0434\u043b\u0435\u043d\u043d\u043e\u0435 \u0430\u0432\u0442\u043e"},
    "rail": {"name": "\ud83d\ude82 \u0416\u0414"},
    "air": {"name": "\u2708\ufe0f \u0410\u0432\u0438\u0430"},
}

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
    if DEV_MODE:
        # Упрощенный вход в режиме разработки
        return {"id": 1, "first_name": "Dev", "username": "devuser"}
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

class BuyRequest(BaseModel):
    text: str

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

@app.get("/api/address")
async def get_address(user=Depends(tg_user_dep)):
    user_id = int(user["id"])
    code = get_user_code(user_id) or get_or_create_user_code(user_id)
    return {"text": CHINA_WAREHOUSE_ADDRESS.format(client_code=code)}

@app.get("/api/deliveries")
async def get_deliveries() -> Dict[str, List[Dict[str, str]]]:
    items = [{"key": k, "name": v.get("name", k)} for k, v in DELIVERY_TYPES.items()]
    return {"items": items}

@app.post("/api/track")
async def add_track_ep(req: TrackRequest, user=Depends(tg_user_dep)):
    user_id = int(user["id"])
    track = (req.track or "").strip().upper()
    if len(track) < 8 or len(track) > 40 or not all(c.isalnum() and c.upper() == c for c in track):
        raise HTTPException(status_code=400, detail="Invalid track format")
    # Сохраняем человекочитаемое название доставки, если ключ известен
    delivery_val = (req.delivery or "").strip()
    delivery_name = DELIVERY_TYPES.get(delivery_val, {}).get("name") if delivery_val in DELIVERY_TYPES else delivery_val
    add_track(user_id, track, delivery_name or "")
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

@app.post("/api/buy")
async def buy_request(req: BuyRequest, user=Depends(tg_user_dep)):
    if not MANAGER_ID:
        return {"ok": True, "sent": False}
    if not BOT_TOKEN or Bot is None:
        raise HTTPException(status_code=500, detail="Bot not available for notifications")
    user_id = int(user.get("id"))
    code = get_user_code(user_id) or get_or_create_user_code(user_id)
    bot = Bot(token=BOT_TOKEN)
    try:
        full_name = f"{user.get('first_name','')} {user.get('last_name','')}".strip()
        username = f"@{user.get('username')}" if user.get('username') else "не указан"
        text = (
            "\ud83d\udecd\ufe0f <b>\u041d\u041e\u0412\u042b\u0419 \u0417\u0410\u041f\u0420\u041e\u0421 \u041d\u0410 \u041f\u041e\u041a\u0423\u041f\u041a\u0423 (Mini App)</b>\n\n"
            f"\ud83c\udd94 \u041a\u043e\u0434 \u043a\u043b\u0438\u0435\u043d\u0442\u0430: <code>{code}</code>\n"
            f"\ud83d\udc64 \u0418\u043c\u044f: {full_name}\n"
            f"\ud83d\udcf1 Username: {username}\n"
            f"\ud83c\udd94 Telegram ID: <code>{user_id}</code>\n\n"
            f"\ud83d\udcdd \u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435: {req.text}"
        )
        await bot.send_message(MANAGER_ID, text, parse_mode="HTML")
    finally:
        await bot.session.close()
    return {"ok": True, "sent": True}

@app.get("/api/tg_photo/{file_id}")
async def proxy_tg_photo(file_id: str):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not set")
    api_base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{api_base}/getFile", params={"file_id": file_id})
        data = r.json()
        if not data.get("ok"):
            raise HTTPException(status_code=404, detail="File not found")
        file_path = data["result"].get("file_path")
        if not file_path:
            raise HTTPException(status_code=404, detail="No file_path")
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        stream = await client.stream("GET", file_url)
        headers = {"Content-Type": stream.headers.get("Content-Type", "application/octet-stream")}
        return StreamingResponse(stream.aiter_raw(), headers=headers)

@app.on_event("startup")
async def _startup():
    try:
        init_db()
    except Exception:
        pass

_base_dir = os.path.dirname(__file__)
_dist_dir = os.path.join(_base_dir, "web", "dist")
_web_dir = os.path.join(_base_dir, "web")
if os.path.isdir(_dist_dir):
    app.mount("/", StaticFiles(directory=_dist_dir, html=True), name="static")
elif os.path.isdir(_web_dir):
    app.mount("/", StaticFiles(directory=_web_dir, html=True), name="static")
