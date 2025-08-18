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
WAREHOUSE_ID = 7095008192  # Замените на реальный ID склада

# Адрес склада в Китае
CHINA_WAREHOUSE_ADDRESS = """Китай, г. Гуанчжоу, район Байюнь
ул. Складская 123, склад 456
Контактное лицо: Иванов Иван
Телефон: +86 123 4567 8910
Ваш код: {user_code}"""

DATA_FILE = "data.json"

def load_data():
    """Загружает данные из файла, создает новый файл если не существует"""
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump({}, f)
        return {}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")
        return {}

def save_data(data):
    """Сохраняет данные в файл"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения данных: {e}")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

class UserStates:
    WAITING_FOR_TRACK = "waiting_for_track"
    WAITING_FOR_ORDER = "waiting_for_order"

async def generate_user_code(user_id, message=None):
    """Генерирует или возвращает существующий код пользователя"""
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
    """Обработчик команды /start"""
    user_code = await generate_user_code(message.from_user.id, message)
    await message.answer(
        f"Привет! Я бот для работы со сборными грузами из Китая.\n\n"
        f"🔑 Ваш личный код: {user_code}\n\n"
        "Доступные команды:\n"
        "/mycod - показать личный код\n"
        "/mytracks - показать все треки\n"
        "/adress - адрес склада\n"
        "/sendtrack - отправить трек-номер\n"
        "/buy - сделать заказ\n"
        "/manager - связаться с менеджером"
    )

@dp.message_handler(commands=['mycod'])
async def show_my_code(message: types.Message):
    """Показывает пользователю его код"""
    try:
        user_code = await generate_user_code(message.from_user.id, message)
        await message.answer(
            f"🔑 Ваш постоянный личный код: {user_code}\n\n"
            f"Используйте его при всех операциях.\n"
            f"Адрес склада: /adress"
        )
    except Exception as e:
        print(f"Ошибка в /mycod: {e}")
        await message.answer("⚠ Произошла ошибка при получении кода")

@dp.message_handler(commands=['mytracks'])
async def show_my_tracks(message: types.Message):
    """Показывает все треки пользователя"""
    try:
        data = load_data()
        user_id = str(message.from_user.id)
        
        if user_id not in data or not data[user_id].get('tracks'):
            await message.answer("У вас пока нет зарегистрированных трек-номеров.")
            return
            
        tracks = data[user_id]['tracks']
        tracks_list = "\n".join(
            f"{i+1}. {t['track']} ({t['date']})" 
            for i, t in enumerate(tracks)
        )
        
        await message.answer(
            f"📦 Ваши трек-номера (всего {len(tracks)}):\n\n"
            f"{tracks_list}"
        )
    except Exception as e:
        print(f"Ошибка в /mytracks: {e}")
        await message.answer("⚠ Произошла ошибка при получении списка треков")

@dp.message_handler(commands=['sendtrack'])
async def send_track(message: types.Message):
    """Начинает процесс добавления трек-номера"""
    try:
        data = load_data()
        user_id = str(message.from_user.id)
        user_code = await generate_user_code(user_id, message)
        
        data[user_id]['state'] = UserStates.WAITING_FOR_TRACK
        save_data(data)
        
        await message.answer(
            f"Отправьте трек-номер для вашего кода {user_code}:\n\n"
            "Формат: буквы и цифры (10-20 символов)\n"
            "Пример: AB123456789CD"
        )
    except Exception as e:
        print(f"Ошибка в /sendtrack: {e}")
        await message.answer("⚠ Ошибка при обработке команды")

@dp.message_handler(regexp=r'^[A-Za-z0-9]{10,20}$')
async def handle_track_number(message: types.Message):
    """Обрабатывает введенный трек-номер"""
    try:
        data = load_data()
        user_id = str(message.from_user.id)
        
        if user_id not in data or data[user_id].get('state') != UserStates.WAITING_FOR_TRACK:
            return
        
        track = message.text.upper()
        user_code = data[user_id]['code']
        full_name = data[user_id].get('full_name', 'Неизвестный клиент')
        
        # Добавляем новый трек
        new_track = {
            "track": track,
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        data[user_id]['tracks'].append(new_track)
        track_count = len(data[user_id]['tracks'])
        
        # Формируем список всех треков
        tracks_history = "\n".join(
            f"{i+1}. {t['track']}" 
            for i, t in enumerate(data[user_id]['tracks'])
        )
        
        # Отправляем уведомление на склад
        await bot.send_message(
            WAREHOUSE_ID,
            f"📦 Поступил новый трек-номер\n\n"
            f"👤 Клиент: {full_name}\n"
            f"🆔 Код: {user_code}\n"
            f"📮 Новый трек: {track}\n"
            f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"🔢 Всего треков: {track_count}\n\n"
            f"📋 История треков:\n{tracks_history}"
        )
        
        # Отправляем подтверждение пользователю с историей
        await message.answer(
            f"✅ Трек-номер {track} успешно добавлен!\n\n"
            f"Ваш код: {user_code}\n"
            f"Всего треков: {track_count}\n\n"
            f"📋 Ваши трек-номера:\n{tracks_history}\n\n"
            f"Для просмотра в любое время: /mytracks"
        )
        
        # Сбрасываем состояние и сохраняем
        data[user_id]['state'] = None
        save_data(data)
        
    except Exception as e:
        print(f"Ошибка обработки трека: {e}")
        await message.answer("⚠ Произошла ошибка при обработке трек-номера")

# ... (остальные обработчики из предыдущего кода)

if __name__ == "__main__":
    # Создаем файл данных если не существует
    if not os.path.exists(DATA_FILE):
        save_data({})
    
    executor.start_polling(dp, skip_updates=True)
