import os
import re
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.utils import executor
from datetime import datetime

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192  # Ваш Telegram ID (должен быть числом)
WAREHOUSE_ID = 7095008192  # Число или строка с ID сотрудника склада

# Полный адрес склада в Китае (замените на реальный)
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

async def generate_user_code(user_id):
    data = load_data()
    user_id = str(user_id)
    if user_id not in data:
        last_code = max([int(v['code'][2:]) for v in data.values()] or [0])
        new_code = f"PR{last_code + 1:05d}"
        data[user_id] = {
            "code": new_code,
            "tracks": [],
            "username": "",
            "full_name": "",
            "state": None
        }
        save_data(data)
    return data[user_id]['code']

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    await message.answer(
        f"Привет! Я бот для работы со сборными грузами из Китая.\n\n"
        f"Ваш личный код: {user_code}\n\n"
        "Доступные команды:\n"
        "/mycod - показать личный код\n"
        "/adress - адрес склада в Китае\n"
        "/sendtrack - отправить трек-номер\n"
        "/buy - сделать заказ\n"
        "/manager - связаться с менеджером"
    )

@dp.message_handler(commands=['mycod'])
async def show_my_code(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    await message.answer(
        f"🔑 Ваш личный код: {user_code}\n\n"
        f"Используйте его при заказе товаров на китайских площадках.\n"
        f"Адрес склада для доставки: /adress"
    )

@dp.message_handler(commands=['adress'])
async def send_address(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    address = CHINA_WAREHOUSE_ADDRESS.format(user_code=user_code)
    await message.answer(f"🏭 Адрес склада в Китае:\n\n{address}")

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

@dp.message_handler(regexp=r'^[A-Za-z0-9]{10,20}$')
async def handle_track_number(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if user_id not in data or data[user_id].get('state') != UserStates.WAITING_FOR_TRACK:
        return
    
    track = message.text.upper()
    user_code = data[user_id]['code']
    
    data[user_id]["tracks"].append({
        "track": track,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    data[user_id]['state'] = None
    save_data(data)
    
    await bot.send_message(
        WAREHOUSE_ID,
        f"📦 Новый трек-номер!\n"
        f"Код клиента: {user_code}\n"
        f"Трек: {track}\n"
        f"Всего треков: {len(data[user_id]['tracks'])}"
    )
    
    await message.answer(f"✅ Трек {track} добавлен к вашему коду {user_code}")

@dp.message_handler(commands=['buy'])
async def start_order(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    data = load_data()
    data[str(message.from_user.id)] = {
        "code": user_code,
        "tracks": data.get(str(message.from_user.id), {}).get("tracks", []),
        "username": message.from_user.username,
        "full_name": message.from_user.full_name,
        "state": UserStates.WAITING_FOR_ORDER
    }
    save_data(data)
    await message.answer(
        f"🛒 Оформление заказа (код: {user_code})\n\n"
        "Что хотите купить и в каком количестве?\n"
        "Можно прикрепить фото или файл с описанием.\n\n"
        "Пример:\n"
        "Футболки черные: 5 шт\n"
        "Джинсы синие: 2 шт"
    )

@dp.message_handler(content_types=[ContentType.TEXT, ContentType.PHOTO, ContentType.DOCUMENT])
async def handle_all_messages(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    # Обработка заказов
    if user_id in data and data[user_id].get('state') == UserStates.WAITING_FOR_ORDER:
        user_code = data[user_id]['code']
        full_name = message.from_user.full_name
        username = f"@{message.from_user.username}" if message.from_user.username else "нет"
        
        # Формируем сообщение для админа
        order_text = message.text if message.text else "Описание в прикрепленных файлах"
        admin_message = (
            f"🛍 Новый заказ!\n\n"
            f"👤 Клиент: {full_name}\n"
            f"📎 Username: {username}\n"
            f"🆔 Код: {user_code}\n\n"
            f"📦 Заказ:\n{order_text}"
        )
        
        try:
            await bot.send_message(ADMIN_ID, admin_message)
            
            # Отправляем вложения если есть
            if message.photo:
                await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, 
                                   caption=f"Фото от {full_name} ({user_code})")
            elif message.document:
                await bot.send_document(ADMIN_ID, message.document.file_id, 
                                      caption=f"Файл от {full_name} ({user_code})")
            
            data[user_id]['state'] = None
            save_data(data)
            await message.answer("✅ Заказ отправлен менеджеру. Ожидайте связи!")
        except Exception as e:
            print(f"Ошибка отправки сообщения админу: {e}")
            await message.answer("❌ Произошла ошибка при отправке заказа. Попробуйте позже.")
        return
    
    # Обработка команды "оператор"
    if message.text and message.text.lower() == "оператор":
        await contact_manager(message)
        return
    
    # Если не распознано - отправляем подсказку
    await message.answer("Не понял ваш запрос. Используйте команды или напишите 'оператор'.")

async def contact_manager(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    full_name = message.from_user.full_name
    username = f"@{message.from_user.username}" if message.from_user.username else "нет"
    
    await message.answer("Менеджер скоро свяжется с вами.")
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📞 Запрос связи с менеджером!\n\n"
            f"👤 Клиент: {full_name}\n"
            f"📎 Username: {username}\n"
            f"🆔 Код: {user_code}\n\n"
            f"Для быстрого ответа: https://t.me/{message.from_user.username}" if message.from_user.username else ""
        )
    except Exception as e:
        print(f"Ошибка отправки сообщения админу: {e}")

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        save_data({})
    
    executor.start_polling(dp, skip_updates=True)
