import os
import re
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.utils import executor
from datetime import datetime

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192  # Ваш Telegram ID (число)
WAREHOUSE_ID = 7095008192  # ID сотрудника склада (число)

# Адрес склада в Китае
CHINA_WAREHOUSE_ADDRESS = """Китай, г. Гуанчжоу, район Байюнь
ул. Складская 123, склад 456
Контактное лицо: Иванов Иван
Телефон: +86 123 4567 8910
Ваш код: {user_code}"""

DATA_FILE = "data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")
        return {}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения данных: {e}")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

class UserStates:
    WAITING_FOR_TRACK = "waiting_for_track"
    WAITING_FOR_ORDER = "waiting_for_order"

async def generate_user_code(user_id):
    data = load_data()
    user_id = str(user_id)
    if user_id not in data:
        last_code = max([int(v['code'][2:]) for v in data.values()] or [0])
        new_code = f"PR{last_code + 1:05d}"
        data[user_id] = {
            "code": new_code,
            "tracks": [],
            "username": message.from_user.username if 'message' in locals() else "",
            "full_name": message.from_user.full_name if 'message' in locals() else "",
            "state": None
        }
        save_data(data)
    return data[user_id]['code']

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    await message.answer(
        f"Привет! Я бот для работы со сборными грузами из Китая.\n\n"
        f"🔑 Ваш личный код: {user_code}\n\n"
        "Доступные команды:\n"
        "/mycod - показать личный код\n"
        "/mytracks - показать все треки\n"
        "/adress - адрес склада\n"
        "/sendtrack - отправить трек\n"
        "/buy - сделать заказ\n"
        "/manager - связаться с менеджером\n\n"
        "Для быстрой связи также можно написать 'оператор'"
    )

@dp.message_handler(commands=['manager'])
async def contact_manager(message: types.Message):
    try:
        user_code = await generate_user_code(message.from_user.id)
        full_name = message.from_user.full_name
        username = f"@{message.from_user.username}" if message.from_user.username else "нет"
        
        # Уведомление пользователю
        await message.answer("✅ Ваш запрос передан менеджеру. Ожидайте ответа в ближайшее время.")
        
        # Уведомление админу
        manager_message = (
            f"📞 ЗАПРОС СВЯЗИ С МЕНЕДЖЕРОМ\n\n"
            f"👤 Клиент: {full_name}\n"
            f"🆔 Код: {user_code}\n"
            f"📎 Username: {username}\n\n"
            f"Для быстрого ответа: https://t.me/{message.from_user.username}" 
            if message.from_user.username else ""
        )
        
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=manager_message
        )
        
    except Exception as e:
        print(f"Ошибка в команде /manager: {e}")
        await message.answer("⚠ Произошла ошибка при отправке запроса. Попробуйте позже.")

# ... (остальные функции из предыдущего кода остаются без изменений)

@dp.message_handler(lambda message: message.text.lower() == 'оператор')
async def handle_operator_request(message: types.Message):
    await contact_manager(message)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        save_data({})
    
    executor.start_polling(dp, skip_updates=True)
