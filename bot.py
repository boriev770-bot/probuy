import os
import re
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.utils import executor
from datetime import datetime

# Конфигурация
TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192  # Ваш ID в Telegram
WAREHOUSE_ID = 7095008192 # ID чата склада
DATA_FILE = "data.json"

# Адрес склада
CHINA_WAREHOUSE_ADDRESS = """Китай, г. Гуанчжоу, район Байюнь
ул. Складская 123, склад 456
Контакт: Иванов Иван
Тел: +86 123 4567 8910
Ваш код: {user_code}"""

# Инициализация бота
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

class UserStates:
    WAITING_FOR_TRACK = "waiting_for_track"
    WAITING_FOR_ORDER = "waiting_for_order"

# Система хранения данных
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения: {e}")

async def get_user_data(user_id, message=None):
    data = load_data()
    user_id = str(user_id)
    if user_id not in data:
        last_code = max([int(v['code'][2:]) for v in data.values()] or [0])
        data[user_id] = {
            "code": f"PR{last_code + 1:05d}",
            "tracks": [],
            "username": message.from_user.username if message else "",
            "full_name": message.from_user.full_name if message else "",
            "state": None
        }
        save_data(data)
    return data[user_id]

# Команды бота
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user = await get_user_data(message.from_user.id, message)
    await message.answer(
        f"👋 Добро пожаловать!\nВаш код: {user['code']}\n\n"
        "Доступные команды:\n"
        "/mycod - ваш код\n"
        "/mytracks - ваши треки\n"
        "/adress - адрес склада\n"
        "/sendtrack - добавить трек\n"
        "/buy - сделать заказ\n"
        "/manager - связаться с менеджером"
    )

@dp.message_handler(commands=['mycod'])
async def cmd_mycod(message: types.Message):
    user = await get_user_data(message.from_user.id)
    await message.answer(f"🔑 Ваш код: {user['code']}")

@dp.message_handler(commands=['mytracks'])
async def cmd_mytracks(message: types.Message):
    user = await get_user_data(message.from_user.id)
    if not user['tracks']:
        await message.answer("У вас нет трек-номеров")
        return
    
    tracks = "\n".join(f"{i+1}. {t['track']}" for i, t in enumerate(user['tracks']))
    await message.answer(f"📦 Ваши треки:\n{tracks}")

@dp.message_handler(commands=['adress'])
async def cmd_adress(message: types.Message):
    user = await get_user_data(message.from_user.id)
    address = CHINA_WAREHOUSE_ADDRESS.format(user_code=user['code'])
    await message.answer(f"🏭 Адрес склада:\n{address}")

@dp.message_handler(commands=['sendtrack'])
async def cmd_sendtrack(message: types.Message):
    user = await get_user_data(message.from_user.id)
    user['state'] = UserStates.WAITING_FOR_TRACK
    save_data(load_data())  # Обновляем данные
    
    await message.answer("Отправьте трек-номер (например: AB123456789CD)")

@dp.message_handler(regexp=r'^[A-Za-z0-9]{10,20}$')
async def handle_track(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if data.get(user_id, {}).get('state') != UserStates.WAITING_FOR_TRACK:
        return
    
    track = message.text.upper()
    user = data[user_id]
    user['tracks'].append({
        "track": track,
        "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    user['state'] = None
    save_data(data)
    
    # Отправка на склад
    await bot.send_message(
        WAREHOUSE_ID,
        f"📦 Новый трек от {user['full_name']}\n"
        f"Код: {user['code']}\n"
        f"Трек: {track}\n"
        f"Всего треков: {len(user['tracks'])}"
    )
    
    await message.answer(f"✅ Трек {track} добавлен!")

@dp.message_handler(commands=['buy'])
async def cmd_buy(message: types.Message):
    user = await get_user_data(message.from_user.id)
    user['state'] = UserStates.WAITING_FOR_ORDER
    save_data(load_data())
    
    await message.answer("Что хотите заказать? Укажите:\n- Название\n- Количество\n- Ссылку (если есть)")

@dp.message_handler(content_types=ContentType.TEXT)
async def handle_order(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if data.get(user_id, {}).get('state') == UserStates.WAITING_FOR_ORDER:
        user = data[user_id]
        await bot.send_message(
            ADMIN_ID,
            f"🛒 Новый заказ от {user['full_name']}\n"
            f"Код: {user['code']}\n\n"
            f"Заказ:\n{message.text}"
        )
        user['state'] = None
        save_data(data)
        await message.answer("✅ Заказ отправлен менеджеру")

@dp.message_handler(commands=['manager'])
async def cmd_manager(message: types.Message):
    user = await get_user_data(message.from_user.id)
    await bot.send_message(
        ADMIN_ID,
        f"📞 Запрос связи от {user['full_name']}\n"
        f"Код: {user['code']}\n"
        f"Username: @{message.from_user.username or 'нет'}"
    )
    await message.answer("✅ Менеджер скоро свяжется с вами")

# Запуск бота
if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        save_data({})
    
    executor.start_polling(dp, skip_updates=True)
