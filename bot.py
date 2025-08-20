import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import asyncio

# --- Константы ---
BOT_TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"  # <-- Вставь свой токен от BotFather
MANAGER_ID = 7095008192       # ID менеджера
WAREHOUSE_ID = 7095008192     # ID склада

# --- Настройка логов ---
logging.basicConfig(level=logging.INFO)

# --- Подключение к БД ---
conn = sqlite3.connect("users.db")
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    client_code TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    track_code TEXT,
    delivery_method TEXT
)''')

conn.commit()

# --- Бот и диспетчер ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Клавиатура выбора доставки ---
def delivery_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚗 Быстрое авто")
    kb.button(text="🚙 Медленное авто")
    kb.button(text="✈ Авиа")
    kb.button(text="🚂 ЖД")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

# --- Получение или создание кода клиента ---
def get_or_create_client_code(user_id: int):
    cursor.execute("SELECT client_code FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0] + 1
    code = f"PB{count:05d}"
    cursor.execute("INSERT INTO users (user_id, client_code) VALUES (?, ?)", (user_id, code))
    conn.commit()
    return code

# --- Старт ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    code = get_or_create_client_code(message.from_user.id)
    await message.answer(f"👋 Добро пожаловать!\nВаш клиентский номер: {code}")

# --- Заказать ---
@dp.message(Command("buy"))
async def buy_cmd(message: types.Message):
    await message.answer("✍ Расскажите, что хотите заказать и в каком количестве?")
    dp.message.register(forward_to_manager)

async def forward_to_manager(message: types.Message):
    user = message.from_user
    code = get_or_create_client_code(user.id)
    text = f"🛒 Новый заказ!
Клиент: {user.full_name} ({user.id})
Код: {code}
Сообщение: {message.text}"
    await bot.send_message(MANAGER_ID, text)
    await message.answer("✅ Ваш запрос отправлен менеджеру.")

# --- Менеджер ---
@dp.message(Command("manager"))
async def manager_cmd(message: types.Message):
    user = message.from_user
    code = get_or_create_client_code(user.id)
    text = f"📩 Запрос к менеджеру!
Клиент: {user.full_name} ({user.id})
Код: {code}
Сообщение: {message.text}"
    await bot.send_message(MANAGER_ID, text)
    await message.answer("✅ Ваш запрос отправлен менеджеру.")

# --- Мой код ---
@dp.message(Command("mycod"))
async def mycod_cmd(message: types.Message):
    code = get_or_create_client_code(message.from_user.id)
    await message.answer(f"🔑 Ваш клиентский номер: {code}")

# --- Отправить трек ---
@dp.message(Command("getcod"))
async def getcod_cmd(message: types.Message):
    await message.answer("📦 Отправьте трек-номер посылки:")
    dp.message.register(process_track)

async def process_track(message: types.Message):
    track = message.text.strip()
    await message.answer("🚚 Выберите способ доставки:", reply_markup=delivery_keyboard())
    dp.message.register(lambda msg: save_track(msg, track))

async def save_track(message: types.Message, track: str):
    delivery = message.text
    user = message.from_user
    code = get_or_create_client_code(user.id)

    cursor.execute("INSERT INTO tracks (user_id, track_code, delivery_method) VALUES (?, ?, ?)",
                   (user.id, track, delivery))
    conn.commit()

    cursor.execute("SELECT track_code, delivery_method FROM tracks WHERE user_id = ?", (user.id,))
    rows = cursor.fetchall()
    history = "\n".join([f"{t} ({d})" for t, d in rows])

    text = (f"✅ Трек {track} ({delivery}) сохранён.\n\n"
            f"📜 История ваших треков:\n{history}")
    await message.answer(text)

    warehouse_text = (f"📦 Новый трек от клиента!\n"
                      f"Клиент: {user.full_name} ({user.id})\n"
                      f"Код: {code}\n"
                      f"Трек: {track} ({delivery})\n\n"
                      f"История треков:\n{history}")
    await bot.send_message(WAREHOUSE_ID, warehouse_text)

# --- Мои треки ---
@dp.message(Command("mytracks"))
async def mytracks_cmd(message: types.Message):
    cursor.execute("SELECT track_code, delivery_method FROM tracks WHERE user_id = ?", (message.from_user.id,))
    rows = cursor.fetchall()
    if not rows:
        await message.answer("📭 У вас пока нет треков.")
        return
    history = "\n".join([f"{t} ({d})" for t, d in rows])
    await message.answer(f"📜 Ваша история треков:\n{history}")

# --- Отмена ---
@dp.message(Command("cancel"))
async def cancel_cmd(message: types.Message):
    dp.message.handlers.clear()
    await message.answer("❌ Действие отменено.")

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
