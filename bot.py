import os
import re
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher, types
from aiogram.types import ContentType, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('china_warehouse_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Получение настроек из переменных окружения
TOKEN = os.getenv('7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI')
MANAGER_ID = int(os.getenv('MANAGER_ID', '7095008192'))
WAREHOUSE_ID = int(os.getenv('WAREHOUSE_ID', '7095008192'))

# Проверка обязательных настроек
if not TOKEN:
    raise ValueError("❌ Не установлен BOT_TOKEN в переменных окружения!")
if not MANAGER_ID:
    raise ValueError("❌ Не установлен MANAGER_ID в переменных окружения!")
if not WAREHOUSE_ID:
    raise ValueError("❌ Не установлен WAREHOUSE_ID в переменных окружения!")

# Файл для хранения данных
DATA_FILE = "china_warehouse_data.json"

# Адрес склада в Китае
CHINA_WAREHOUSE_ADDRESS = """🏭 <b>АДРЕС СКЛАДА В КИТАЕ</b>

📍 <b>Адрес:</b>
中国广东省广州市白云区
Китай, провинция Гуандун, г. Гуанчжоу, район Байюнь
ул. Складская, д. 123, склад №456

📞 <b>Контакты склада:</b>
Менеджер: Ван Минг (王明)
Телефон: +86 138 0013 8000
WeChat: warehouse_manager_123

🔑 <b>ВАШ ЛИЧНЫЙ КОД КЛИЕНТА:</b> <code>{client_code}</code>

⚠️ <b>ВАЖНО!</b> 
При заказе товаров ОБЯЗАТЕЛЬНО указывайте ваш код клиента <code>{client_code}</code> в поле "Получатель" или "Дополнительная информация"

📦 <b>Как указывать код:</b>
• В поле получатель: "Wang Ming {client_code}"
• В комментарии к заказу: "Warehouse code: {client_code}"
• В любом поле где можно указать дополнительную информацию

🚚 <b>Доступные способы доставки в Москву:</b>
• 🚛 Быстрое авто (7-10 дней)
• 🚚 Медленное авто (15-20 дней)  
• ✈️ Авиа (3-5 дней)
• 🚂 ЖД (10-14 дней)"""

# Инициализация бота
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=storage)

# Блокировка для безопасной работы с файлами
file_lock = asyncio.Lock()

# Состояния пользователя
class UserStates(StatesGroup):
    waiting_for_track = State()
    choosing_delivery = State()
    waiting_for_order = State()

# Типы доставки
DELIVERY_TYPES = {
    "fast_auto": {"name": "🚛 Быстрое авто", "days": "7-10 дней", "description": "Быстрая доставка автотранспортом"},
    "slow_auto": {"name": "🚚 Медленное авто", "days": "15-20 дней", "description": "Экономичная доставка автотранспортом"},
    "avia": {"name": "✈️ Авиа", "days": "3-5 дней", "description": "Самая быстрая доставка авиапочтой"},
    "railway": {"name": "🚂 ЖД", "days": "10-14 дней", "description": "Доставка железнодорожным транспортом"}
}

# Безопасная работа с файлом данных
@asynccontextmanager
async def safe_file_access():
    async with file_lock:
        yield

# Загрузка данных из файла
async def load_data():
    async with safe_file_access():
        try:
            if not os.path.exists(DATA_FILE):
                logger.info("Файл данных не найден, создаю новый")
                return {}
            
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Загружены данные для {len(data)} клиентов")
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка при загрузке данных: {e}")
            return {}

# Сохранение данных в файл
async def save_data(data):
    async with safe_file_access():
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Данные сохранены для {len(data)} клиентов")
        except IOError as e:
            logger.error(f"Ошибка при сохранении данных: {e}")
            raise

# Получение или создание клиента
async def get_or_create_client(user_id, message=None):
    data = await load_data()
    user_id = str(user_id)
    
    if user_id not in data:
        # Генерация нового кода клиента PB00001, PB00002 и т.д.
        existing_codes = []
        for client in data.values():
            if client.get('client_code', '').startswith('PB'):
                try:
                    code_num = int(client['client_code'][2:])
                    existing_codes.append(code_num)
                except (ValueError, IndexError):
                    continue
        
        last_code = max(existing_codes) if existing_codes else 0
        new_client_code = f"PB{last_code + 1:05d}"
        
        client_data = {
            "client_code": new_client_code,
            "tracks": [],
            "orders": [],
            "username": message.from_user.username if message else "",
            "full_name": message.from_user.full_name if message else "",
            "phone": "",
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat()
        }
        
        data[user_id] = client_data
        await save_data(data)
        
        logger.info(f"Создан новый клиент: {client_data['full_name']} ({new_client_code})")
        
        # Уведомление менеджера о новом клиенте
        try:
            await bot.send_message(
                MANAGER_ID,
                f"👤 <b>НОВЫЙ КЛИЕНТ ЗАРЕГИСТРИРОВАН</b>\n\n"
                f"🆔 Код клиента: <code>{new_client_code}</code>\n"
                f"👤 Имя: {client_data['full_name']}\n"
                f"📱 Username: @{client_data['username'] or 'не указан'}\n"
                f"🆔 Telegram ID: <code>{user_id}</code>\n"
                f"📅 Дата регистрации: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                parse_mode='HTML'
            )
        except Exception as e:
        logger.error(f"Не удалось вызвать менеджера: {e}")
        await message.answer(
            "❌ <b>Временная ошибка</b>\n\n"
            "Не удалось связаться с менеджером.\n"
            "Попробуйте через несколько минут или напишите напрямую.",
            parse_mode='HTML'
        )

# Команда помощи
@dp.message_handler(commands=['help'], state='*')
async def cmd_help(message: types.Message, state: FSMContext):
    await state.finish()
    
    help_text = """ℹ️ <b>СПРАВКА ПО ИСПОЛЬЗОВАНИЮ БОТА</b>

🔑 <b>Мой код клиента</b>
Показывает ваш персональный код для заказов

📦 <b>Мои треки</b>  
Список всех ваших зарегистрированных треков

📍 <b>Адрес склада</b>
Полный адрес склада в Китае с вашим кодом

🚚 <b>Добавить трек</b>
Регистрация нового трек-номера с выбором доставки

🛒 <b>Заказать товар</b>
Заказ товаров через байера (профессиональный покупатель)

👨‍💼 <b>Вызвать менеджера</b>
Связь с менеджером для решения вопросов

📝 <b>ВАЖНЫЕ ПРАВИЛА:</b>

1️⃣ <b>При заказе товаров</b> ВСЕГДА указывайте ваш код клиента
2️⃣ <b>Проверяйте трек-номера</b> перед добавлением
3️⃣ <b>Выбирайте подходящий тип доставки</b> (быстро/дешево)
4️⃣ <b>Подробно описывайте заказы</b> через байера

❓ <b>Проблемы?</b> Используйте /start для сброса или вызовите менеджера"""
    
    await message.answer(help_text, parse_mode='HTML')

# Статистика для менеджера
@dp.message_handler(commands=['stats'])
async def show_stats(message: types.Message):
    if message.from_user.id != MANAGER_ID:
        return
    
    data = await load_data()
    if not data:
        await message.answer("📊 <b>Статистика системы:</b>\n\nПока нет клиентов", parse_mode='HTML')
        return
    
    total_tracks = sum(len(client.get('tracks', [])) for client in data.values())
    total_orders = sum(len(client.get('orders', [])) for client in data.values())
    
    stats_text = f"📊 <b>СТАТИСТИКА СИСТЕМЫ</b>\n\n"
    stats_text += f"👥 Всего клиентов: {len(data)}\n"
    stats_text += f"📦 Всего треков: {total_tracks}\n"
    stats_text += f"🛒 Всего заказов: {total_orders}\n\n"
    stats_text += f"📋 <b>Последние 10 клиентов:</b>\n"
    
    # Сортируем клиентов по дате регистрации
    sorted_clients = sorted(data.items(), 
                          key=lambda x: x[1].get('created_at', ''), 
                          reverse=True)[:10]
    
    for i, (user_id, client) in enumerate(sorted_clients, 1):
        stats_text += (f"{i}. {client['client_code']} - {client['full_name']}\n"
                      f"   📦 Треков: {len(client.get('tracks', []))}, "
                      f"🛒 Заказов: {len(client.get('orders', []))}\n")
    
    await message.answer(stats_text, parse_mode='HTML')

# Обработка неизвестных сообщений
@dp.message_handler(content_types=ContentType.TEXT, state='*')
async def handle_unknown_message(message: types.Message, state: FSMContext):
    await state.finish()
    
    await message.answer(
        "❓ <b>Команда не распознана</b>\n\n"
        "Используйте кнопки меню для навигации\n"
        "или команду /help для справки",
        parse_mode='HTML'
    )
    await show_main_menu(message)

# Обработка ошибок
@dp.errors_handler()
async def errors_handler(update, exception):
    logger.error(f"Произошла ошибка: {exception}")
    
    if update.message:
        try:
            await update.message.answer(
                "❌ <b>Произошла техническая ошибка</b>\n\n"
                "Попробуйте:\n"
                "• Использовать команду /start\n"
                "• Повторить действие через минуту\n"
                "• Обратиться к менеджеру\n\n"
                "Приносим извинения за неудобство!",
                parse_mode='HTML'
            )
        except:
            pass
    
    return True

# События запуска и остановки
async def on_startup(dp):
    logger.info("🤖 Бот для китайского склада запущен!")
    
    # Создание файла данных если не существует
    if not os.path.exists(DATA_FILE):
        await save_data({})
        logger.info("Создан новый файл данных")
    
    # Уведомление менеджера о запуске бота
    try:
        await bot.send_message(
            MANAGER_ID,
            "🤖 <b>БОТ КИТАЙСКОГО СКЛАДА ЗАПУЩЕН</b>\n\n"
            "✅ Система готова к работе!\n"
            f"📅 Время запуска: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить менеджера о запуске: {e}")

async def on_shutdown(dp):
    logger.info("🔴 Бот останавливается...")
    
    try:
        await bot.send_message(
            MANAGER_ID,
            "🔴 <b>БОТ ОСТАНОВЛЕН</b>\n\n"
            f"📅 Время остановки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            parse_mode='HTML'
        )
    except:
        pass
    
    await dp.storage.close()
    await dp.storage.wait_closed()

# Запуск бота
if __name__ == "__main__":
    try:
        logger.info("Запуск бота для китайского склада...")
        executor.start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown
        )
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}")
        print(f"❌ ОШИБКА: {e}")
        print("\n🔧 ПРОВЕРЬТЕ:")
        print("1. Установлен ли BOT_TOKEN в переменных окружения")
        print("2. Установлен ли MANAGER_ID в переменных окружения") 
        print("3. Установлен ли WAREHOUSE_ID в переменных окружения")
        print("4. Установлена ли библиотека aiogram: pip install aiogram"):
            logger.error(f"Не удалось уведомить менеджера о новом клиенте: {e}")
    
    # Обновление времени последней активности
    data[user_id]["last_activity"] = datetime.now().isoformat()
    await save_data(data)
    
    return data[user_id]

# Проверка валидности трек-номера
def is_valid_track_number(track):
    track = track.upper().strip()
    patterns = [
        r'^[A-Z]{2}\d{9}[A-Z]{2}$',
        r'^[A-Z]{1}\d{10}$',
        r'^[0-9]{10,20}$',
        r'^[A-Z0-9]{8,30}$'
    ]
    return any(re.match(pattern, track) for pattern in patterns) and len(track.strip()) >= 8

# Создание клавиатуры с типами доставки
def create_delivery_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    for key, delivery in DELIVERY_TYPES.items():
        keyboard.add(InlineKeyboardButton(
            f"{delivery['name']} ({delivery['days']})",
            callback_data=f"delivery_{key}"
        ))
    keyboard.add(InlineKeyboardButton("❌ Отменить", callback_data="cancel_delivery"))
    return keyboard

# Главное меню
async def show_main_menu(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        types.KeyboardButton("🔑 Мой код клиента"),
        types.KeyboardButton("📦 Мои треки")
    )
    keyboard.add(
        types.KeyboardButton("📍 Адрес склада"),
        types.KeyboardButton("🚚 Добавить трек")
    )
    keyboard.add(
        types.KeyboardButton("🛒 Заказать товар"),
        types.KeyboardButton("👨‍💼 Вызвать менеджера")
    )
    
    await message.answer(
        "🏠 <b>Главное меню</b>\n\n"
        "Выберите нужное действие:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

# Команда /start
@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    
    client = await get_or_create_client(message.from_user.id, message)
    
    welcome_text = f"""🇨🇳 <b>Добро пожаловать в систему выкупа с китайских маркетплейсов!</b>

🔑 <b>Ваш личный код клиента:</b> <code>{client['client_code']}</code>

📋 <b>Что вы можете делать:</b>
• Получить адрес склада в Китае
• Добавлять трек-номера ваших посылок
• Выбирать способ доставки в Москву
• Заказывать товары через байера
• Связываться с менеджером

⚠️ <b>Важно запомнить:</b>
Ваш код <code>{client['client_code']}</code> нужно указывать при каждом заказе на китайских сайтах!

Выберите действие в меню ниже 👇"""
    
    await message.answer(welcome_text, parse_mode='HTML')
    await show_main_menu(message)

# Показать код клиента
@dp.message_handler(lambda message: message.text == "🔑 Мой код клиента", state='*')
async def show_client_code(message: types.Message, state: FSMContext):
    await state.finish()
    client = await get_or_create_client(message.from_user.id)
    
    await message.answer(
        f"🔑 <b>Ваш личный код клиента:</b>\n\n"
        f"<code>{client['client_code']}</code>\n\n"
        f"📋 <b>Как использовать:</b>\n"
        f"• При заказе товаров указывайте этот код в поле получателя\n"
        f"• Или добавляйте в комментарии к заказу\n"
        f"• Без этого кода посылка может потеряться!\n\n"
        f"💡 <b>Совет:</b> Сохраните этот код в заметки телефона",
        parse_mode='HTML'
    )

# Показать треки клиента
@dp.message_handler(lambda message: message.text == "📦 Мои треки", state='*')
async def show_client_tracks(message: types.Message, state: FSMContext):
    await state.finish()
    client = await get_or_create_client(message.from_user.id)
    
    if not client['tracks']:
        await message.answer(
            "📦 <b>У вас пока нет зарегистрированных треков</b>\n\n"
            "Используйте кнопку '🚚 Добавить трек' для добавления первого трек-номера",
            parse_mode='HTML'
        )
        return
    
    tracks_text = f"📦 <b>Ваши зарегистрированные треки:</b>\n\n"
    
    for i, track_info in enumerate(client['tracks'], 1):
        delivery_info = DELIVERY_TYPES.get(track_info.get('delivery_type', ''), {})
        tracks_text += f"<b>{i}.</b> <code>{track_info['track']}</code>\n"
        tracks_text += f"   🚚 {delivery_info.get('name', 'Не указано')}\n"
        tracks_text += f"   📅 Добавлен: {track_info['date'][:16]}\n\n"
    
    tracks_text += f"📊 <b>Всего треков:</b> {len(client['tracks'])}"
    
    await message.answer(tracks_text, parse_mode='HTML')

# Показать адрес склада
@dp.message_handler(lambda message: message.text == "📍 Адрес склада", state='*')
async def show_warehouse_address(message: types.Message, state: FSMContext):
    await state.finish()
    client = await get_or_create_client(message.from_user.id)
    
    address = CHINA_WAREHOUSE_ADDRESS.format(client_code=client['client_code'])
    
    await message.answer(address, parse_mode='HTML')

# Начать добавление трека
@dp.message_handler(lambda message: message.text == "🚚 Добавить трек", state='*')
async def add_track_start(message: types.Message):
    client = await get_or_create_client(message.from_user.id)
    
    await UserStates.waiting_for_track.set()
    
    tracks_info = ""
    if client['tracks']:
        tracks_info = f"\n📦 <b>Ваши текущие треки:</b>\n"
        for i, track_info in enumerate(client['tracks'], 1):
            delivery_info = DELIVERY_TYPES.get(track_info.get('delivery_type', ''), {})
            tracks_info += f"{i}. <code>{track_info['track']}</code> ({delivery_info.get('name', 'Не указано')})\n"
        tracks_info += "\n"
    
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("❌ Отменить"))
    
    await message.answer(
        f"🚚 <b>Добавление нового трек-номера</b>{tracks_info}\n"
        f"📝 Отправьте трек-номер вашей посылки\n\n"
        f"<b>Примеры правильных форматов:</b>\n"
        f"• <code>RB123456789CN</code>\n"
        f"• <code>CP123456789CN</code>\n" 
        f"• <code>1234567890123</code>\n"
        f"• <code>YT1234567890123456</code>\n\n"
        f"⚠️ Проверьте правильность номера!",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

# Обработка ввода трек-номера
@dp.message_handler(state=UserStates.waiting_for_track)
async def handle_track_input(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить":
        await state.finish()
        await message.answer("❌ Добавление трека отменено")
        await show_main_menu(message)
        return
    
    track_number = message.text.strip().upper()
    
    if not is_valid_track_number(track_number):
        await message.answer(
            "❌ <b>Неправильный формат трек-номера!</b>\n\n"
            "Трек-номер должен:\n"
            "• Содержать 8-30 символов\n"
            "• Состоять из латинских букв и цифр\n"
            "• Быть без пробелов и спецсимволов\n\n"
            "Попробуйте еще раз или нажмите 'Отменить'",
            parse_mode='HTML'
        )
        return
    
    # Проверка на дублирование
    data = await load_data()
    user_id = str(message.from_user.id)
    client = data[user_id]
    
    existing_tracks = [t['track'] for t in client['tracks']]
    if track_number in existing_tracks:
        await message.answer(
            f"⚠️ <b>Трек-номер уже зарегистрирован!</b>\n\n"
            f"Трек <code>{track_number}</code> уже есть в вашем списке.\n"
            f"Попробуйте добавить другой трек-номер.",
            parse_mode='HTML'
        )
        return
    
    await state.update_data(track_number=track_number)
    await UserStates.choosing_delivery.set()
    
    await message.answer(
        f"✅ Трек-номер <code>{track_number}</code> принят\n\n"
        f"🚚 <b>Выберите способ доставки в Москву:</b>",
        reply_markup=create_delivery_keyboard(),
        parse_mode='HTML'
    )

# Обработка выбора типа доставки
@dp.callback_query_handler(lambda c: c.data.startswith('delivery_'), state=UserStates.choosing_delivery)
async def handle_delivery_choice(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    
    if callback_query.data == "cancel_delivery":
        await state.finish()
        await callback_query.message.edit_text("❌ Добавление трека отменено")
        await show_main_menu(callback_query.message)
        return
    
    delivery_type = callback_query.data.replace('delivery_', '')
    delivery_info = DELIVERY_TYPES[delivery_type]
    
    state_data = await state.get_data()
    track_number = state_data['track_number']
    
    data = await load_data()
    user_id = str(callback_query.from_user.id)
    client = data[user_id]
    
    track_data = {
        "track": track_number,
        "delivery_type": delivery_type,
        "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "status": "Зарегистрирован"
    }
    
    client['tracks'].append(track_data)
    await save_data(data)
    
    # Отправляем информацию на склад
    try:
        warehouse_message = (
            f"📦 <b>НОВЫЙ ТРЕК-НОМЕР</b>\n\n"
            f"🆔 Код клиента: <code>{client['client_code']}</code>\n"
            f"👤 Клиент: {client['full_name']}\n"
            f"📱 Username: @{client['username'] or 'не указан'}\n\n"
            f"📋 Трек-номер: <code>{track_number}</code>\n"
            f"🚚 Тип доставки: {delivery_info['name']} ({delivery_info['days']})\n"
            f"📅 Дата регистрации: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📊 Всего треков у клиента: {len(client['tracks'])}"
        )
        
        await bot.send_message(WAREHOUSE_ID, warehouse_message, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Не удалось отправить информацию на склад: {e}")
    
    await state.finish()
    
    confirmation_text = (
        f"✅ <b>Трек-номер успешно зарегистрирован!</b>\n\n"
        f"📋 Трек: <code>{track_number}</code>\n"
        f"🚚 Доставка: {delivery_info['name']} ({delivery_info['days']})\n\n"
        f"📦 <b>Все ваши треки:</b>\n"
    )
    
    for i, track_info in enumerate(client['tracks'], 1):
        delivery = DELIVERY_TYPES.get(track_info.get('delivery_type', ''), {})
        confirmation_text += f"{i}. <code>{track_info['track']}</code> ({delivery.get('name', 'Не указано')})\n"
    
    await callback_query.message.edit_text(confirmation_text, parse_mode='HTML')
    await show_main_menu(callback_query.message)

# Начать заказ товара
@dp.message_handler(lambda message: message.text == "🛒 Заказать товар", state='*')
async def start_order(message: types.Message):
    await UserStates.waiting_for_order.set()
    
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("❌ Отменить"))
    
    await message.answer(
        "🛒 <b>Заказ товара через байера</b>\n\n"
        "📝 Опишите подробно что хотите заказать:\n\n"
        "🔸 <b>Обязательно укажите:</b>\n"
        "• Название товара или ссылку\n"
        "• Количество штук\n"
        "• Размер/цвет (если важно)\n"
        "• Примерная цена за штуку\n"
        "• Особые пожелания\n\n"
        "📱 Можете отправить фото товара или скриншот страницы\n\n"
        "💡 <b>Пример:</b>\n"
        "\"Нужно заказать iPhone 15 Pro черный 256GB, 1 штука, цена около $1000, обязательно оригинал с гарантией\"",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

# Обработка заказа
@dp.message_handler(state=UserStates.waiting_for_order, content_types=[ContentType.TEXT, ContentType.PHOTO])
async def handle_order_input(message: types.Message, state: FSMContext):
    if message.text == "❌ Отменить":
        await state.finish()
        await message.answer("❌ Заказ отменен")
        await show_main_menu(message)
        return
    
    order_text = message.text or message.caption or ""
    
    if len(order_text.strip()) < 10:
        await message.answer(
            "❌ <b>Слишком короткое описание!</b>\n\n"
            "Опишите подробнее что хотите заказать.\n"
            "Чем больше деталей - тем точнее будет заказ.",
            parse_mode='HTML'
        )
        return
    
    data = await load_data()
    user_id = str(message.from_user.id)
    client = data[user_id]
    
    order_data = {
        "text": order_text,
        "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "status": "Отправлен менеджеру",
        "has_photo": message.photo is not None
    }
    
    if 'orders' not in client:
        client['orders'] = []
    client['orders'].append(order_data)
    await save_data(data)
    
    try:
        manager_message = (
            f"🛒 <b>НОВЫЙ ЗАКАЗ ЧЕРЕЗ БАЙЕРА</b>\n\n"
            f"🆔 Код клиента: <code>{client['client_code']}</code>\n"
            f"👤 Клиент: {client['full_name']}\n"
            f"📱 Username: @{client['username'] or 'не указан'}\n"
            f"🆔 Telegram ID: <code>{user_id}</code>\n\n"
            f"📝 <b>Описание заказа:</b>\n{order_text}\n\n"
            f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"📊 Всего заказов от клиента: {len(client['orders'])}"
        )
        
        if message.photo:
            await bot.send_photo(
                MANAGER_ID, 
                message.photo[-1].file_id,
                caption=manager_message,
                parse_mode='HTML'
            )
        else:
            await bot.send_message(MANAGER_ID, manager_message, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Не удалось отправить заказ менеджеру: {e}")
        await message.answer("❌ Ошибка отправки заказа. Попробуйте позже.")
        return
    
    await state.finish()
    
    await message.answer(
        "✅ <b>Заказ успешно отправлен менеджеру!</b>\n\n"
        "👨‍💼 Менеджер получил ваш заказ и свяжется с вами в ближайшее время для:\n"
        "• Уточнения деталей\n" 
        "• Расчета стоимости\n"
        "• Согласования условий\n\n"
        "⏱ <b>Время ответа:</b> обычно в течение 1-2 часов в рабочее время",
        parse_mode='HTML'
    )
    await show_main_menu(message)

# Вызвать менеджера
@dp.message_handler(lambda message: message.text == "👨‍💼 Вызвать менеджера", state='*')
async def call_manager(message: types.Message, state: FSMContext):
    await state.finish()
    client = await get_or_create_client(message.from_user.id, message)
    
    try:
        manager_message = (
            f"📞 <b>КЛИЕНТ ВЫЗЫВАЕТ МЕНЕДЖЕРА</b>\n\n"
            f"🆔 Код клиента: <code>{client['client_code']}</code>\n"
            f"👤 Клиент: {client['full_name']}\n"
            f"📱 Username: @{message.from_user.username or 'не указан'}\n"
            f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n\n"
            f"📊 <b>Статистика клиента:</b>\n"
            f"• Треков зарегистрировано: {len(client['tracks'])}\n"
            f"• Заказов сделано: {len(client.get('orders', []))}\n"
            f"• Дата регистрации: {client['created_at'][:10]}\n\n"
            f"📅 Время обращения: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await bot.send_message(MANAGER_ID, manager_message, parse_mode='HTML')
        
        await message.answer(
            "✅ <b>Менеджер вызван!</b>\n\n"
            "👨‍💼 Менеджер получил уведомление о вашем обращении\n"
            "📞 Он свяжется с вами в ближайшее время\n\n"
            "⏱ <b>Обычное время ответа:</b> 15-30 минут в рабочее время\n"
            "🕐 <b>Рабочее время:</b> 09:00 - 18:00 по московскому времени",
            parse_mode='HTML'
        )
        
    except Exception as e