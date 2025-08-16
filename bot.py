import os
import re
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192  # ID администратора
WAREHOUSE_ID = 7095008192  # Замените на реальный ID сотрудника склада

# Здесь укажите полный адрес склада в Китае
CHINA_WAREHOUSE_ADDRESS = """ВСТАВЬ_ПОЛНЫЙ_АДРЕС_СКЛАДА_В_КИТАЕ
Например:
Китай, г. Гуанчжоу, район Байюнь, 
ул. Складская 123, склад 456, 
Контактное лицо: Иванов Иван
Телефон: +86 123 4567 8910
Ваш код: PR00001 (укажите свой код)"""

DATA_FILE = "data.json"

# Варианты доставки
DELIVERY_OPTIONS = {
    "🚗 Быстрое авто": "Быстрая автодоставка (10-15 дней)",
    "🚛 Медленное авто": "Медленная автодоставка (15-20 дней)",
    "✈️ Авиа": "Авиадоставка (5-7 дней)",
    "🚂 ЖД": "Железнодорожная доставка (18-25 дней)"
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "Привет! Я бот для работы со сборными грузами из Китая.\n\n"
        "Доступные команды:\n"
        "/getcod - получить личный номер\n"
        "/adress - адрес склада в Китае\n"
        "/sendtrack - отправить трек-номер\n\n"
        "Для связи с оператором напишите 'оператор'"
    )

@dp.message_handler(commands=['getcod'])
async def get_code(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if user_id not in data:
        # Генерируем новый код PR00001, PR00002 и т.д.
        last_code = max([int(v['code'][2:]) for v in data.values()] or [0])
        new_code = f"PR{last_code + 1:05d}"
        
        data[user_id] = {
            "code": new_code,
            "tracks": [],
            "username": message.from_user.username,
            "full_name": message.from_user.full_name
        }
        save_data(data)
        
        await message.answer(
            f"✅ Вам присвоен личный номер: {new_code}\n\n"
            f"Используйте его при заказе товаров на китайских площадках.\n"
            f"Адрес склада для доставки: /adress"
        )
    else:
        await message.answer(f"Ваш личный номер: {data[user_id]['code']}")

@dp.message_handler(commands=['adress'])
async def send_address(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if user_id in data:
        personal_code = data[user_id]['code']
        address_with_code = CHINA_WAREHOUSE_ADDRESS.replace("PR00001", personal_code)
    else:
        address_with_code = CHINA_WAREHOUSE_ADDRESS
    
    await message.answer(
        f"🏭 Адрес склада в Китае:\n\n{address_with_code}\n\n"
        "Указывайте этот адрес при заказе товаров.\n"
        "Не забудьте указать ваш личный код!"
    )

@dp.message_handler(commands=['sendtrack'])
async def send_track(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if user_id not in data:
        await message.answer("Сначала получите личный номер через /getcod")
        return
    
    # Создаем клавиатуру с вариантами доставки
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [KeyboardButton(option) for option in DELIVERY_OPTIONS.keys()]
    kb.add(*buttons)
    
    await message.answer("Выберите способ доставки из Китая:", reply_markup=kb)

@dp.message_handler(lambda m: m.text in DELIVERY_OPTIONS.keys())
async def process_delivery_choice(message: types.Message):
    dp.delivery_choice = message.text
    await message.answer(
        f"Вы выбрали: {DELIVERY_OPTIONS[message.text]}\n\n"
        "Теперь отправьте трек-номер посылки:",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    text = message.text.lower()
    user_id = str(message.from_user.id)
    data = load_data()
    
    # Обработка запроса оператора
    if text == "оператор":
        await message.answer("Оператор скоро свяжется с вами.")
        await bot.send_message(
            ADMIN_ID,
            f"📩 Запрос к оператору!\n"
            f"Клиент: {message.from_user.full_name}\n"
            f"Username: @{message.from_user.username or 'нет'}\n"
            f"Код: {data.get(user_id, {}).get('code', 'нет кода')}\n"
            f"Сообщение: {message.text}"
        )
        return
    
    # Обработка трек-номеров
    if hasattr(dp, "delivery_choice"):
        if user_id not in data:
            await message.answer("Сначала получите личный номер через /getcod")
            return
            
        track = message.text.upper().strip()
        
        # Проверка формата трек-номера (базовая)
        if not re.match(r"^[A-Z0-9]{10,20}$", track):
            await message.answer("❌ Неверный формат трек-номера. Попробуйте еще раз.")
            return
            
        # Добавляем трек в базу
        data[user_id]["tracks"].append({
            "track": track,
            "delivery": dp.delivery_choice,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        save_data(data)
        
        # Отправляем уведомление на склад
        await bot.send_message(
            WAREHOUSE_ID,
            f"📦 Новый трек-номер!\n"
            f"Клиент: {data[user_id]['full_name']}\n"
            f"Код: {data[user_id]['code']}\n"
            f"Трек: {track}\n"
            f"Способ доставки: {DELIVERY_OPTIONS[dp.delivery_choice]}\n"
            f"Всего треков у клиента: {len(data[user_id]['tracks'])}"
        )
        
        await message.answer(
            f"✅ Трек-номер {track} успешно добавлен!\n"
            f"Способ доставки: {DELIVERY_OPTIONS[dp.delivery_choice]}\n\n"
            f"Вы можете добавить еще трек-номер командой /sendtrack"
        )
        del dp.delivery_choice
        return
    
    await message.answer("Не понял ваш запрос. Используйте команды или напишите 'оператор'.")

if __name__ == "__main__":
    # Создаем файл данных, если его нет
    if not os.path.exists(DATA_FILE):
        save_data({})
        
    executor.start_polling(dp, skip_updates=True)
