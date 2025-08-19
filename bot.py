import os
import re
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI
"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "7095008192"))
WAREHOUSE_ID = int(os.getenv("WAREHOUSE_ID", "7095008192"))

DB_FILE = "data.json"

# Загружаем базу
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        db = json.load(f)
else:
    db = {"users": {}, "last_code": 0}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def generate_client_code():
    db["last_code"] += 1
    return f"PR{db['last_code']:05d}"

FAQ = {
    r"(сдела.*|заказ.*)": "Для заказа напишите слово 'оператор' или используйте /manager.",
    r"(сколь.*|стои.*|доставк.*цена.*|цена.*доставк.*)": "Стоимость доставки рассчитывается индивидуально. Напишите 'оператор'.",
    r"(время.*|срок.*|когда.*придет.*|через.*дней.*|сроки.*доставк.*)": "Сроки: быстрое авто 10–15 дней, медленное авто 15–20 дней (Москва, рынок Южные Ворота)."
}

def find_best_match(user_text):
    user_text = user_text.lower()
    for pattern, answer in FAQ.items():
        if re.search(pattern, user_text):
            return answer
    return None

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "Привет! Я бот для заказов.\n"
        "Команды:\n"
        "/getcod — получить личный код\n"
        "/adress — адрес склада\n"
        "/sendtrack — отправить трек\n"
        "/manager — связаться с оператором"
    )

@dp.message_handler(commands=["getcod"])
async def get_cod(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in db["users"]:
        code = generate_client_code()
        db["users"][user_id] = {"code": code, "tracks": []}
        save_db()
        await message.answer(f"Ваш личный код: {code}")
    else:
        await message.answer(f"Ваш код уже есть: {db['users'][user_id]['code']}")

@dp.message_handler(commands=["adress"])
async def adress(message: types.Message):
    await message.answer("📦 Адрес склада: ВСТАВЬТЕ_АДРЕС_СКЛАДА")

@dp.message_handler(commands=["sendtrack"])
async def send_track(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Быстрое авто"), KeyboardButton("Медленное авто"))
    await message.answer("Выберите способ доставки:", reply_markup=kb)

@dp.message_handler(lambda msg: msg.text in ["Быстрое авто", "Медленное авто"])
async def process_delivery(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in db["users"]:
        await message.answer("Сначала получите код через /getcod")
        return
    db["users"][user_id]["last_delivery"] = message.text
    save_db()
    await message.answer("Теперь отправьте трек номер.", reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(commands=["manager"])
async def manager(message: types.Message):
    await bot.send_message(
        ADMIN_ID,
        f"📩 Запрос к оператору!\n"
        f"Имя: {message.from_user.full_name}\n"
        f"Username: @{message.from_user.username if message.from_user.username else 'нет'}"
    )
    await message.answer("Оператор скоро свяжется с вами.")

@dp.message_handler()
async def handle_message(message: types.Message):
    user_id = str(message.from_user.id)
    text = message.text.strip()

    if len(text) >= 5 and any(ch.isdigit() for ch in text):
        if user_id not in db["users"]:
            await message.answer("Сначала получите код через /getcod")
            return
        delivery = db["users"][user_id].get("last_delivery")
        if not delivery:
            await message.answer("Сначала выберите доставку через /sendtrack")
            return

        db["users"][user_id]["tracks"].append({"track": text, "delivery": delivery})
        save_db()

        await bot.send_message(
            WAREHOUSE_ID,
            f"📦 Новый трек!\n"
f"Клиент: {db['users'][user_id]['code']}\n"
            f"Доставка: {delivery}\n"
            f"Трек: {text}"
        )

        tracks = db["users"][user_id]["tracks"]
        history = "\\n".join([f"{t['track']} ({t['delivery']})" for t in tracks])
        await message.answer(f"Ваш трек сохранён!\\nИстория ваших треков:\\n{history}")
        return

    response = find_best_match(text)
    if response:
        await message.answer(response)
    else:
        await message.answer("Извини, я не нашёл ответа. Напишите 'оператор' или /manager.")

if name == "__main__":
    asyncio.run(dp.start_polling())
