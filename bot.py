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

DELIVERY_OPTIONS = {
    "🚗 Быстрое авто": "Быстрая автодоставка (10-15 дней)",
    "🚛 Медленное авто": "Медленная автодоставка (15-20 дней)",
    "✈️ Авиа": "Авиадоставка (5-7 дней)",
    "🚂 ЖД": "Железнодорожная доставка (18-25 дней)"
}

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

class UserStates:
    WAITING_FOR_TRACK = "waiting_for_track"
    WAITING_FOR_DELIVERY = "waiting_for_delivery"
    WAITING_FOR_ORDER_DETAILS = "waiting_for_order_details"

# Команда /start
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "Привет! Я бот для работы со сборными грузами из Китая.\n\n"
        "Доступные команды:\n"
        "/getcod - получить личный номер\n"
        "/adress - адрес склада в Китае\n"
        "/sendtrack - отправить трек-номер\n"
        "/buy - сделать заказ\n"
        "/manager - связаться с менеджером\n\n"
        "Для быстрой связи также можно написать 'оператор'"
    )

# Команда /buy - оформление заказа
@dp.message_handler(commands=['buy'])
async def start_order(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    # Проверяем есть ли у пользователя код
    if user_id not in data:
        await message.answer("Сначала получите личный номер через /getcod")
        return
    
    # Устанавливаем состояние ожидания деталей заказа
    data[user_id]['state'] = UserStates.WAITING_FOR_ORDER_DETAILS
    save_data(data)
    
    await message.answer(
        "📦 Оформление заказа\n\n"
        "Напишите что хотите заказать и в каком количестве?\n"
        "Можно прикрепить фото или файл с описанием товара.\n\n"
        "Пример:\n"
        "Футболки черные, размеры S-5шт, M-3шт, L-2шт\n"
        "Джинсы синие 2шт\n"
        "Кроссовки белые 42 размер - 1 пара"
    )

# Обработчик для деталей заказа (текст + файлы)
@dp.message_handler(content_types=[ContentType.TEXT, ContentType.PHOTO, ContentType.DOCUMENT], 
                    state=UserStates.WAITING_FOR_ORDER_DETAILS)
async def process_order_details(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if user_id not in data or data[user_id].get('state') != UserStates.WAITING_FOR_ORDER_DETAILS:
        return
    
    # Формируем сообщение для админа
    order_info = f"🛒 Новый заказ!\n\n" \
                 f"Клиент: {data[user_id]['full_name']}\n" \
                 f"Код: {data[user_id]['code']}\n" \
                 f"Username: @{message.from_user.username or 'нет'}\n\n" \
                 f"Детали заказа:\n{message.text if message.text else 'См. вложения'}"
    
    # Отправляем текст заказа
    await bot.send_message(ADMIN_ID, order_info)
    
    # Если есть фото или файл - пересылаем их админу
    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, 
                           caption=f"Фото от {data[user_id]['full_name']}")
    elif message.document:
        await bot.send_document(ADMIN_ID, message.document.file_id, 
                              caption=f"Файл от {data[user_id]['full_name']}")
    
    # Сбрасываем состояние
    data[user_id]['state'] = None
    save_data(data)
    
    await message.answer(
        "✅ Ваш заказ принят! Менеджер свяжется с вами для уточнения деталей.\n\n"
        "Вы можете сделать еще один заказ через /buy или отправить трек-номер через /sendtrack"
    )

# Команда /manager - связь с менеджером (аналог "оператор")
@dp.message_handler(commands=['manager'])
async def contact_manager(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    user_code = data.get(user_id, {}).get('code', 'нет кода')
    
    await message.answer("Менеджер скоро свяжется с вами.")
    await bot.send_message(
        ADMIN_ID,
        f"📞 Запрос связи с менеджером!\n"
        f"Клиент: {message.from_user.full_name}\n"
        f"Username: @{message.from_user.username or 'нет'}\n"
        f"Код: {user_code}\n\n"
        f"Для быстрого ответа: https://t.me/{message.from_user.username}" if message.from_user.username else ""
    )

# ... (остальные обработчики из предыдущего кода остаются без изменений)

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        save_data({})
        
    executor.start_polling(dp, skip_updates=True)
