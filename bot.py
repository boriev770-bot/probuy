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

async def generate_user_code(user_id, message=None):
    data = load_data()
    user_id = str(user_id)
    if user_id not in data:
        last_code = max([int(v['code'][2:]) for v in data.values()] or [0])
        new_code = f"PR{last_code + 1:05d}"
        data[user_id] = {
            "code": new_code,
            "tracks": [],
            "username": message.from_user.username if message else "",
            "full_name": message.from_user.full_name if message else "",
            "state": None
        }
        save_data(data)
    return data[user_id]['code']

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_code = await generate_user_code(message.from_user.id, message)
    await message.answer(
        f"Привет! Я бот для работы со сборными грузами из Китая.\n\n"
        f"🔑 Ваш личный код: {user_code}\n\n"
        "Доступные команды:\n"
        "/mycod - показать личный код\n"
        "/mytracks - показать все треки\n"
        "/adress - адрес склада в Китае\n"
        "/sendtrack - отправить трек-номер\n"
        "/buy - сделать заказ\n"
        "/manager - связаться с менеджером"
    )

@dp.message_handler(commands=['adress'])
async def send_address(message: types.Message):
    try:
        user_code = await generate_user_code(message.from_user.id, message)
        address = CHINA_WAREHOUSE_ADDRESS.format(user_code=user_code)
        await message.answer(
            f"🏭 Адрес нашего склада в Китае:\n\n{address}\n\n"
            f"Указывайте этот адрес при заказе товаров вместе с вашим кодом: {user_code}"
        )
    except Exception as e:
        print(f"Ошибка в /adress: {e}")
        await message.answer("⚠ Произошла ошибка при получении адреса")

@dp.message_handler(commands=['buy'])
async def start_order(message: types.Message):
    try:
        user_code = await generate_user_code(message.from_user.id, message)
        data = load_data()
        user_id = str(message.from_user.id)
        
        data[user_id] = {
            "code": user_code,
            "tracks": data.get(user_id, {}).get("tracks", []),
            "username": message.from_user.username,
            "full_name": message.from_user.full_name,
            "state": UserStates.WAITING_FOR_ORDER
        }
        save_data(data)
        
        await message.answer(
            f"🛒 Оформление заказа (код: {user_code})\n\n"
            "Отправьте список товаров, которые хотите заказать:\n"
            "- Название товара\n"
            "- Количество\n"
            "- Ссылку на товар (если есть)\n\n"
            "Можно прикрепить фото или файл с описанием."
        )
    except Exception as e:
        print(f"Ошибка в /buy: {e}")
        await message.answer("⚠ Произошла ошибка при оформлении заказа")

@dp.message_handler(content_types=[ContentType.TEXT, ContentType.PHOTO, ContentType.DOCUMENT])
async def handle_order_details(message: types.Message):
    try:
        data = load_data()
        user_id = str(message.from_user.id)
        
        if user_id not in data or data[user_id].get('state') != UserStates.WAITING_FOR_ORDER:
            return
        
        user_code = data[user_id]['code']
        full_name = data[user_id]['full_name']
        username = f"@{data[user_id]['username']}" if data[user_id]['username'] else "нет"
        
        # Получаем описание заказа
        if message.text:
            order_text = message.text
        elif message.caption:
            order_text = message.caption
        else:
            order_text = "Описание в прикрепленных файлах"
        
        # Отправляем заказ админу
        await bot.send_message(
            ADMIN_ID,
            f"🛍 НОВЫЙ ЗАКАЗ\n\n"
            f"👤 Клиент: {full_name}\n"
            f"📎 Username: {username}\n"
            f"🆔 Код: {user_code}\n\n"
            f"📦 Заказ:\n{order_text}"
        )
        
        # Отправляем вложения если есть
        if message.photo:
            await bot.send_photo(
                ADMIN_ID,
                message.photo[-1].file_id,
                caption=f"Фото к заказу {user_code}"
            )
        elif message.document:
            await bot.send_document(
                ADMIN_ID,
                message.document.file_id,
                caption=f"Файл к заказу {user_code}"
            )
        
        # Подтверждение пользователю
        await message.answer(
            "✅ Ваш заказ получен! Менеджер свяжется с вами для уточнения деталей.\n\n"
            f"Ваш код заказа: {user_code}"
        )
        
        # Сбрасываем состояние
        data[user_id]['state'] = None
        save_data(data)
        
    except Exception as e:
        print(f"Ошибка обработки заказа: {e}")
        await message.answer("⚠ Произошла ошибка при обработке заказа")

@dp.message_handler(commands=['manager'])
async def contact_manager(message: types.Message):
    try:
        user_code = await generate_user_code(message.from_user.id, message)
        full_name = message.from_user.full_name
        username = f"@{message.from_user.username}" if message.from_user.username else "нет"
        
        await message.answer(
            "✅ Ваш запрос передан менеджеру. Ожидайте ответа в ближайшее время.\n\n"
            f"Ваш код: {user_code}"
        )
        
        await bot.send_message(
            ADMIN_ID,
            f"📞 ЗАПРОС СВЯЗИ С МЕНЕДЖЕРОМ\n\n"
            f"👤 Клиент: {full_name}\n"
            f"📎 Username: {username}\n"
            f"🆔 Код: {user_code}\n\n"
            f"Для быстрого ответа: https://t.me/{message.from_user.username}"
            if message.from_user.username else ""
        )
    except Exception as e:
        print(f"Ошибка в /manager: {e}")
        await message.answer("⚠ Произошла ошибка при отправке запроса")

# ... (другие обработчики из предыдущего кода остаются без изменений)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        save_data({})
    
    executor.start_polling(dp, skip_updates=True)
