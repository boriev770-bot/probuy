import os
import re
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.utils import executor
from datetime import datetime

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192  # Ваш Telegram ID
WAREHOUSE_ID = 123456789  # ID сотрудника склада (число)

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
        f"🔑 Ваш личный код: {user_code}\n\n"
        "Доступные команды:\n"
        "/mycod - показать личный код\n"
        "/mytracks - показать все ваши треки\n"
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

@dp.message_handler(commands=['mytracks'])
async def show_my_tracks(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if user_id in data and data[user_id].get('tracks'):
        tracks_list = "\n".join(
            f"{idx+1}. {track['track']} ({track['date']})" 
            for idx, track in enumerate(data[user_id]['tracks'])
        )
        await message.answer(
            f"📦 Ваши трек-номера (всего {len(data[user_id]['tracks'])}):\n\n"
            f"{tracks_list}"
        )
    else:
        await message.answer("У вас пока нет зарегистрированных трек-номеров.")

@dp.message_handler(commands=['adress'])
async def send_address(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    address = CHINA_WAREHOUSE_ADDRESS.format(user_code=user_code)
    await message.answer(f"🏭 Адрес склада в Китае:\n\n{address}")

@dp.message_handler(commands=['sendtrack'])
async def send_track(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    user_code = await generate_user_code(user_id)
    
    data[user_id]['state'] = UserStates.WAITING_FOR_TRACK
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
    full_name = data[user_id].get('full_name', message.from_user.full_name)
    
    # Инициализация списка треков если нужно
    if 'tracks' not in data[user_id]:
        data[user_id]['tracks'] = []
    
    # Добавляем новый трек
    new_track = {
        "track": track,
        "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    data[user_id]['tracks'].append(new_track)
    track_count = len(data[user_id]['tracks'])
    
    try:
        # Формируем сообщение для склада
        warehouse_msg = (
            f"📦 ПОСТУПИЛ НОВЫЙ ТРЕК-НОМЕР\n\n"
            f"▪ Код клиента: {user_code}\n"
            f"▪ Имя: {full_name}\n"
            f"▪ Трек: {track}\n"
            f"▪ Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"▪ Всего треков у клиента: {track_count}\n"
            f"▪ История треков: {', '.join(t['track'] for t in data[user_id]['tracks'])}"
        )
        
        # Отправляем на склад
        await bot.send_message(
            chat_id=WAREHOUSE_ID,
            text=warehouse_msg
        )
        
        # Подтверждение пользователю
        await message.answer(
            f"✅ Трек-номер успешно зарегистрирован!\n\n"
            f"Ваш код: {user_code}\n"
            f"Текущий трек: {track}\n"
            f"Всего ваших треков: {track_count}"
        )
        
    except Exception as e:
        print(f"Ошибка отправки на склад: {e}")
        await message.answer(
            "⚠ Не удалось отправить трек на склад. "
            "Администратор уведомлен о проблеме."
        )
        await bot.send_message(
            ADMIN_ID,
            f"🚨 Ошибка отправки трека!\n"
            f"Клиент: {full_name} ({user_code})\n"
            f"Трек: {track}\n"
            f"Ошибка: {str(e)}"
        )
    
    # Сохраняем данные
    data[user_id]['state'] = None
    save_data(data)

@dp.message_handler(commands=['buy'])
async def start_order(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
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
        "Что хотите заказать и в каком количестве?\n"
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
        full_name = data[user_id].get('full_name', message.from_user.full_name)
        username = f"@{message.from_user.username}" if message.from_user.username else "нет"
        
        order_description = message.caption or message.text or "Описание в прикрепленных файлах"
        
        try:
            # Отправляем основное сообщение
            admin_msg = await bot.send_message(
                ADMIN_ID,
                f"🛍 НОВЫЙ ЗАКАЗ\n\n"
                f"👤 Клиент: {full_name}\n"
                f"📎 Username: {username}\n"
                f"🆔 Код: {user_code}\n\n"
                f"📦 Заказ:\n{order_description}"
            )
            
            # Отправляем вложения
            if message.photo:
                await bot.send_photo(
                    ADMIN_ID,
                    message.photo[-1].file_id,
                    reply_to_message_id=admin_msg.message_id
                )
            elif message.document:
                await bot.send_document(
                    ADMIN_ID,
                    message.document.file_id,
                    reply_to_message_id=admin_msg.message_id
                )
            
            await message.answer("✅ Заказ отправлен менеджеру. Ожидайте связи!")
        except Exception as e:
            print(f"Ошибка отправки заказа: {e}")
            await message.answer("❌ Ошибка при отправке заказа. Попробуйте позже.")
        
        # Сохраняем данные
        data[user_id]['state'] = None
        save_data(data)
        return
    
    # Обработка команды "оператор"
    if message.text and message.text.lower() == "оператор":
        await contact_manager(message)
        return
    
    await message.answer("Не понял ваш запрос. Используйте команды или напишите 'оператор'.")

async def contact_manager(message: types.Message):
    user_code = await generate_user_code(message.from_user.id)
    full_name = message.from_user.full_name
    username = f"@{message.from_user.username}" if message.from_user.username else "нет"
    
    await message.answer("Менеджер скоро свяжется с вами.")
    try:
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
        print(f"Ошибка отправки запроса менеджеру: {e}")

if __name__ == "__main__":
    # Создаем файл данных если его нет
    if not os.path.exists(DATA_FILE):
        save_data({})
    
    executor.start_polling(dp, skip_updates=True)
