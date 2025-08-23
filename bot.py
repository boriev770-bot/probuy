import os
import logging
from typing import List, Optional, Tuple

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from database import init_db, get_or_create_user_code, get_tracks, add_track


# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("china_warehouse_bot")


# Переменные окружения
BOT_TOKEN = os.getenv("7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI
")
# По вашему запросу — по умолчанию обе переменные одинаковые (можно переопределить в Railway)
MANAGER_ID = int(os.getenv("MANAGER_ID", "7095008192") or 7095008192)
WAREHOUSE_ID = int(os.getenv("WAREHOUSE_ID", "7095008192") or 7095008192)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


# Плейсхолдер адреса склада — замените этот текст на реальный адрес
CHINA_WAREHOUSE_ADDRESS = (
    "🏭 <b>АДРЕС СКЛАДА В КИТАЕ</b>\n\n"
    "⬇️ ВСТАВЬТЕ НИЖЕ ВАШ РЕАЛЬНЫЙ АДРЕС СКЛАДА (замените этот текст) ⬇️\n"
    "<i>Пример формата: Китай, провинция ..., г. ..., район ..., ул. ..., склад №...</i>\n\n"
    "🔑 <b>ВАШ ЛИЧНЫЙ КОД КЛИЕНТА:</b> <code>{client_code}</code>\n"
)


# Инициализация бота
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=storage)


# Состояния
class TrackStates(StatesGroup):
    waiting_for_track = State()


class BuyStates(StatesGroup):
    waiting_for_details = State()


def format_tracks(tracks: List[Tuple[str, Optional[str]]]) -> str:
    if not tracks:
        return "Нет зарегистрированных трек-кодов"
    lines: List[str] = []
    for idx, (track, delivery) in enumerate(tracks, start=1):
        suffix = f" ({delivery})" if delivery else ""
        lines.append(f"{idx}. <code>{track}</code>{suffix}")
    return "\n".join(lines)


@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    welcome = (
        f"🇨🇳 <b>Добро пожаловать!</b>\n\n"
        f"🔑 Ваш личный код клиента: <code>{code}</code>\n\n"
        f"Доступные команды:\n"
        f"/getcod — получить личный код\n"
        f"/adress — адрес склада в Китае\n"
        f"/sendtrack — отправить трек-код\n"
        f"/buy — оформить заказ через менеджера\n"
        f"/mycod — список ваших трек-кодов\n"
        f"/manager — связаться с менеджером\n"
    )
    await message.answer(welcome, parse_mode="HTML")
    await message.answer("✅ Команда выполнена.")


@dp.message_handler(commands=["getcod"], state="*")
async def cmd_getcod(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    await message.answer(f"🔑 Ваш личный код клиента: <code>{code}</code>", parse_mode="HTML")
    await message.answer("✅ Команда выполнена.")


@dp.message_handler(commands=["adress"], state="*")
async def cmd_address(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    await message.answer(CHINA_WAREHOUSE_ADDRESS.format(client_code=code), parse_mode="HTML")
    await message.answer("✅ Команда выполнена.")


def is_valid_track_number(text: str) -> bool:
    t = (text or "").strip().upper()
    if len(t) < 8 or len(t) > 40:
        return False
    # Мягкая проверка: разрешены латинские буквы и цифры, без специальных символов
    return all("A" <= c <= "Z" or "0" <= c <= "9" for c in t)


@dp.message_handler(commands=["sendtrack"], state="*")
async def cmd_sendtrack(message: types.Message, state: FSMContext):
    await state.finish()
    get_or_create_user_code(message.from_user.id)  # ensure code exists
    tracks = get_tracks(message.from_user.id)

    if tracks:
        await message.answer(
            "📦 Ваша история зарегистрированных трек-кодов:\n\n" + format_tracks(tracks),
            parse_mode="HTML",
        )
    await message.answer("✅ Команда принята. 📝 Отправьте следующий трек-код одним сообщением. Для отмены — /cancel")
    await TrackStates.waiting_for_track.set()


@dp.message_handler(commands=["cancel"], state="*")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("❌ Действие отменено.")


@dp.message_handler(state=TrackStates.waiting_for_track, content_types=types.ContentTypes.TEXT)
async def handle_track_input(message: types.Message, state: FSMContext):
    track = (message.text or "").strip().upper()
    if not is_valid_track_number(track):
        await message.answer("⚠️ Неверный формат трек-кода. Пришлите другой или /cancel")
        return

    # Сохраняем в БД
    add_track(message.from_user.id, track)

    # Готовим информацию
    code = get_or_create_user_code(message.from_user.id)
    tracks = get_tracks(message.from_user.id)
    full_name = message.from_user.full_name or ""
    username = f"@{message.from_user.username}" if message.from_user.username else "не указан"

    # Пересылаем сотруднику склада с инфо о пользователе и всеми треками
    if WAREHOUSE_ID:
        try:
            text = (
                "📦 <b>НОВЫЙ ТРЕК-КОД</b>\n\n"
                f"🆔 Код клиента: <code>{code}</code>\n"
                f"👤 Имя: {full_name}\n"
                f"📱 Username: {username}\n"
                f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n\n"
                f"📋 Текущий трек: <code>{track}</code>\n\n"
                "📚 Все треки пользователя:\n" + format_tracks(tracks)
            )
            await bot.send_message(WAREHOUSE_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify warehouse: %s", e)

    await state.finish()
    await message.answer("✅ Трек-код получен и передан сотруднику склада.")


@dp.message_handler(commands=["buy"], state="*")
async def cmd_buy(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("✅ Команда принята. 🛒 Что вы хотите заказать и в каком количестве? Опишите в следующем сообщении. Для отмены — /cancel")
    await BuyStates.waiting_for_details.set()


@dp.message_handler(state=BuyStates.waiting_for_details, content_types=[types.ContentType.TEXT, types.ContentType.PHOTO])
async def handle_buy_details(message: types.Message, state: FSMContext):
    text = message.caption or message.text or ""
    if len(text.strip()) < 3:
        await message.answer("⚠️ Сообщение слишком короткое. Опишите заказ подробнее или /cancel")
        return

    code = get_or_create_user_code(message.from_user.id)
    full_name = message.from_user.full_name or ""
    username = f"@{message.from_user.username}" if message.from_user.username else "не указан"

    notify = (
        "🛒 <b>НОВЫЙ ЗАПРОС НА ПОКУПКУ</b>\n\n"
        f"🆔 Код клиента: <code>{code}</code>\n"
        f"👤 Имя: {full_name}\n"
        f"📱 Username: {username}\n"
        f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n\n"
        f"📝 Сообщение клиента:\n{text}"
    )

    if MANAGER_ID:
        try:
            if message.photo:
                await bot.send_photo(MANAGER_ID, message.photo[-1].file_id, caption=notify, parse_mode="HTML")
            else:
                await bot.send_message(MANAGER_ID, notify, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify manager: %s", e)

    await state.finish()
    await message.answer("✅ Ваш запрос отправлен менеджеру. Он свяжется с вами.")


@dp.message_handler(commands=["mycod"], state="*")
async def cmd_mycod(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    tracks = get_tracks(message.from_user.id)
    text = (
        f"🔑 Ваш код клиента: <code>{code}</code>\n\n"
        + ("📦 Ваши трек-коды:\n\n" + format_tracks(tracks) if tracks else "Пока нет зарегистрированных трек-кодов")
    )
    await message.answer(text, parse_mode="HTML")
    await message.answer("✅ Команда выполнена.")


@dp.message_handler(commands=["manager"], state="*")
async def cmd_manager(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    full_name = message.from_user.full_name or ""
    username = f"@{message.from_user.username}" if message.from_user.username else "не указан"

    if MANAGER_ID:
        try:
            text = (
                "📞 <b>КЛИЕНТ ХОЧЕТ СВЯЗАТЬСЯ С МЕНЕДЖЕРОМ</b>\n\n"
                f"🆔 Код клиента: <code>{code}</code>\n"
                f"👤 Имя: {full_name}\n"
                f"📱 Username: {username}\n"
                f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n"
            )
            await bot.send_message(MANAGER_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify manager: %s", e)

    await message.answer("✅ Сообщение менеджеру отправлено. Ожидайте контакт.")


@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Неизвестная команда. Доступно: /start, /getcod, /adress, /sendtrack, /buy, /mycod, /manager")


async def on_startup(dp: Dispatcher):
    init_db()
    try:
        if MANAGER_ID:
            await bot.send_message(MANAGER_ID, "🤖 Бот запущен")
    except Exception:
        pass


async def on_shutdown(dp: Dispatcher):
    try:
        if MANAGER_ID:
            await bot.send_message(MANAGER_ID, "🔴 Бот остановлен")
    except Exception:
        pass


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
# database.py
import sqlite3
from typing import List, Optional, Tuple

DB_PATH = "database.db"


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
