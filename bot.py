import os
import re
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.utils import executor
from datetime import datetime

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192
WAREHOUSE_ID = 7095008192

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
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

class UserStates:
    WAITING_FOR_TRACK = "waiting_for_track"
    WAITING_FOR_ORDER = "waiting_for_order"

# Генерация кода пользователя
async def generate_user_code(user_id):
    data = load_data()
    if str(user_id) not in data:
        last_code = max([int(v['code'][2:]) for v in data.values()] or [0])
        new_code = f"PR{last_code + 1:05d}"
        data[str(user_id)] = {
            "code": new_code,
            "tracks": [],
            "username": "",
            "full_name": "",
            "state": None
        }
        save_data(data)
    return data[str(user_id)]['code']

# Команда /start
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    await message.answer(
        f"Привет! Ваш постоянный личный код: {user_code}\n\n"
        "Доступные команды:\n"
        "/adress - адрес склада в Китае\n"
        "/sendtrack - отправить трек-номер\n"
        "/buy - сделать заказ\n"
        "/manager - связаться с менеджером"
    )

# Команда /adress
@dp.message_handler(commands=['adress'])
async def send_address(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    address = CHINA_WAREHOUSE_ADDRESS.format(user_code=user_code)
    await message.answer(f"🏭 Адрес склада в Китае:\n\n{address}")

# Команда /sendtrack - упрощенная версия
@dp.message_handler(commands=['sendtrack'])
async def send_track(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    data = load_data()
    data[str(message.from_user.id)]['state'] = UserStates.WAITING_FOR_TRACK
    save_data(data)
    await message.answer(
        f"Отправьте трек-номер для вашего кода {user_code}:\n\n"
        "Пример: AB123456789CD"
    )

# Обработчик трек-номеров
@dp.message_handler(regexp=r'^[A-Za-z0-9]{10,20}$')
async def handle_track_number(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if user_id not in data or data[user_id].get('state') != UserStates.WAITING_FOR_TRACK:
        return
    
    track = message.text.upper()
    user_code = data[user_id]['code']
    
    # Добавляем трек
    data[user_id]["tracks"].append({
        "track": track,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    data[user_id]['state'] = None
    save_data(data)
    
    # Отправляем на склад
    await bot.send_message(
        WAREHOUSE_ID,
        f"📦 Новый трек-номер!\n"
        f"Код клиента: {user_code}\n"
        f"Трек: {track}\n"
        f"Всего треков: {len(data[user_id]['tracks'])}"
    )
    
    await message.answer(f"✅ Трек {track} добавлен к вашему коду {user_code}")

# Команда /buy - упрощенная версия
@dp.message_handler(commands=['buy'])
async def start_order(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    data = load_data()
    data[str(message.from_user.id)]['state'] = UserStates.WAITING_FOR_ORDER
    save_data(data)
    await message.answer(
        f"🛒 Оформление заказа (код: {user_code})\n\n"
        "Что хотите купить и в каком количестве?\n"
        "Можно прикрепить фото или файл с описанием.\n\n"
        "Пример:\n"
        "Футболки черные: 5 шт\n"
        "Джинсы синие: 2 шт"
    )

# Обработчик заказов
@dp.message_handler(content_types=[ContentType.TEXT, ContentType.PHOTO, ContentType.DOCUMENT])
async def handle_order(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if user_id not in data or data[user_id].get('state') != UserStates.WAITING_FOR_ORDER:
        return
    
    user_code = data[user_id]['code']
    order_text = message.text or "См. вложения"
    
    # Формируем сообщение для админа
    order_msg = f"🛍 Новый заказ!\n\n" \
                f"Код: {user_code}\n" \
                f"Клиент: @{message.from_user.username or 'нет'}\n" \
                f"Заказ:\n{order_text}"
    
    await bot.send_message(ADMIN_ID, order_msg)
    
    # Пересылаем вложения
    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id)
    elif message.document:
        await bot.send_document(ADMIN_ID, message.document.file_id)
    
    data[user_id]['state'] = None
    save_data(data)
    
    await message.answer("✅ Заказ отправлен менеджеру. Ожидайте связи!")

# Команда /manager
@dp.message_handler(commands=['manager'])
async def contact_manager(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    await message.answer("Менеджер скоро свяжется с вами.")
    await bot.send_message(
        ADMIN_ID,
        f"📞 Запрос связи (код: {user_code})\n"
        f"Клиент: @{message.from_user.username or message.from_user.full_name}\n"
        f"Ссылка: https://t.me/{message.from_user.username}" if message.from_user.username else ""
    )

if __name__ == "__main__":
    # Создаем файл данных при первом запуске
    if not os.path.exists(DATA_FILE):
        save_data({})
    
    executor.start_polling(dp, skip_updates=True)
