вот что там есть Deploy
Custom Start Command
Command that will be run to start new deployments. Docs↗
Start command
bash start.sh
Add pre-deploy step (Docs↗)
Thought for 15s
Проблема в том, что Railway запускает не python bot.py, а то, что указано в “Custom Start Command”: bash start.sh. Из‑за этого стартует старый скрипт/старый файл.

Сделай так, очень по шагам.

Способ 1 (самый простой): запусти напрямую python bot.py

Открой Railway → Project → твой Service.
Перейди во вкладку Deploy (там где “Custom Start Command”).
В поле “Start command” замени текст:
было: bash start.sh
нужно: python bot.py
Нажми Save/Deploy.
Дальше: Settings → Rebuild without cache (или Clear cache → Deploy).
Открой Logs и проверь, что видишь строки:
RUNNING FILE: /app/bot.py
Start polling.
Способ 2: использовать Procfile (рекомендую для бота как worker)

В репозитории на GitHub убедись, что в корне есть файл Procfile со строкой:
worker: python bot.py
В Railway: в Deploy → поле “Start command” ОЧИСТИ (оставь пустым), чтобы использовался Procfile.
Если бот лежит не в корне репо, зайди в Service → Settings → Monorepo → Root Directory и укажи папку, где лежат bot.py и Procfile.
Settings → Rebuild without cache → Deploy.
В Logs смотри запуск.
Если хочешь оставить web (не обязательно):

В Procfile поставь web: python bot.py и добавь в начало bot.py маленький HTTP‑сервер (healthcheck), чтобы Railway не гасил контейнер:
import os, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
def run_healthcheck():
    port = int(os.getenv("PORT", "8080"))
    HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler).serve_forever()
threading.Thread(target=run_healthcheck, daemon=True).start()
Если хочешь оставить start.sh:

Открой файл start.sh в репозитории и замени содержимое на:
#!/usr/bin/env bash
set -euo pipefail
python bot.py
В Railway → Deploy → “Start command” оставь bash start.sh (как у тебя), но после правки обязательно Rebuild without cache.
Обязательные проверки после изменений

Variables (Service → Settings → Variables):
BOT_TOKEN: твой токен (строка из BotFather, без кавычек)
MANAGER_ID: 7095008192
WAREHOUSE_ID: 7095008192
requirements.txt: aiogram==2.25.1
В bot.py инициализация именно такая:
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
Нигде не осталось dp = Dispatcher(7095008192).
Как убедиться, что запускается нужный файл

В начале bot.py оставь строки:
import os, logging
logging.basicConfig(level=logging.INFO)
logging.info(f"RUNNING FILE: {os.path.abspath(__file__)}")
В Logs увидишь: RUNNING FILE: /app/bot.py
Если после этого всё равно не запускается:

Пришли скрин страницы Deploy с “Start command”, скрин Variables и первые 20 строк bot.py. Я скажу, что именно поправить.
все работает 
Thought for 3s
Отлично! Рад, что всё запустилось.

Что сделать дальше
Вставьте реальный адрес склада в CHINA_WAREHOUSE_ADDRESS в bot.py.
Проверьте все команды в Telegram: /start, /getcod, /adress, /sendtrack, /buy, /mycod, /manager.
Не храните токен в коде — только в Railway Variables.
Хотите, чтобы данные не терялись? Используйте Volume (или вынесем БД в PostgreSQL — могу переделать).
Следите за логами в Railway → Logs; при правках делайте Rebuild without cache.
Нужно добавить новые функции (например, удаление треков, админ-статистику, inline‑кнопки, подтверждения менеджера)? Скажите — сделаю.

в логах это выскакивает 
2025-08-23 22:40:31,140 INFO aiogram: Bot: Probuy bot [@Probuychine_bot]

2025-08-23 22:40:31,146 WARNING aiogram: Updates were skipped successfully.

2025-08-23 22:40:31,168 INFO aiogram.dispatcher.dispatcher: Start polling.
Thought for 6s
Это нормально.

INFO Bot …: бот запустился и авторизовался.
WARNING Updates were skipped successfully.: это потому что в коде стоит skip_updates=True — бот пропустил старые сообщения, которые копились, и будет обрабатывать только новые.
INFO Start polling.: бот слушает новые сообщения и готов к работе.
Хочешь не пропускать старые апдейты? Поменяй запуск на:

executor.start_polling(dp, skip_updates=False, on_startup=on_startup, on_shutdown=on_shutdown)
Но обычно skip_updates=True — правильно, чтобы не было “залпа” старых команд после деплоя.

мы можем сделать интерактивное меню в боте ? 
Thought for 11s
Да. Есть два удобных варианта (можно совместить):

Постоянное меню (ReplyKeyboard): кнопки внизу чата
Предлагаю: "🔑 Код", "📍 Адрес", "📦 Мои треки", "🚚 Добавить трек", "🛒 Заказать", "👨‍💼 Менеджер".
Встроенные кнопки (InlineKeyboard): под сообщениями
Примеры: выбор типа доставки после трека, список треков с кнопками “Показать/Удалить”, подтверждение отправки заказа.
Скажи:

Какие пункты точно добавить в нижнее меню?
Нужны ли встроенные кнопки для треков (история, удаление, подробности) и заказа?
Оставляем эти иконки/подписи или поменять?
точно нужно добавить: заказать, менеджер, получить код, получить адрес, отправить трек, мои треки. иконки можешь подобрать сам.
давай после трека добавим еще выбор типа доставки: быстрое авто, медленное авто, жд, авиа с кнопками подтверждения заказа после выбора типа доставки
Thought for 22s
Готово. Вот обновленный bot.py с интерактивным меню и выбором типа доставки + подтверждение регистрации трека.

# bot.py
import os
import logging
from typing import List, Optional, Tuple

from aiogram import Bot, Dispatcher, types
from aiogram.types import ContentType, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from database import init_db, get_or_create_user_code, get_tracks, add_track


# Логи
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("china_warehouse_bot")
logging.info("RUNNING FILE: %s", os.path.abspath(__file__))


# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
MANAGER_ID = int(os.getenv("MANAGER_ID", "7095008192") or 7095008192)
WAREHOUSE_ID = int(os.getenv("WAREHOUSE_ID", "7095008192") or 7095008192)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


# Плейсхолдер адреса склада — замените этот текст на реальный адрес
CHINA_WAREHOUSE_ADDRESS = (
    "🏭 <b>АДРЕС СКЛАДА В КИТАЕ</b>\n\n"
    "⬇️ ВСТАВЬТЕ НИЖЕ ВАШ РЕАЛЬНЫЙ АДРЕС СКЛАДА (замените этот текст) ⬇️\n"
    "<i>Пример формата: Китай, провинция ..., г. ..., район ..., ул. ..., склад №...</i>\n\n"
    "🔑 <b>ВАШ ЛИЧНЫЙ КОД КЛИЕНТА:</b> <code>{client_code}</code>\n"
)


# Бот
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


# Состояния
class TrackStates(StatesGroup):
    waiting_for_track = State()
    choosing_delivery = State()
    confirming = State()


class BuyStates(StatesGroup):
    waiting_for_details = State()


# Меню (ReplyKeyboard)
def get_main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("🛒 Заказать"),
        KeyboardButton("👨‍💼 Менеджер"),
        KeyboardButton("🔑 Получить код"),
        KeyboardButton("📍 Получить адрес"),
        KeyboardButton("🚚 Отправить трек"),
        KeyboardButton("📦 Мои треки"),
    )
    return kb


# Доставка (Inline)
DELIVERY_TYPES = {
    "fast_auto": {"name": "🚛 Быстрое авто"},
    "slow_auto": {"name": "🚚 Медленное авто"},
    "rail": {"name": "🚂 ЖД"},
    "air": {"name": "✈️ Авиа"},
}


def delivery_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for key, info in DELIVERY_TYPES.items():
        kb.add(InlineKeyboardButton(info["name"], callback_data=f"delivery_{key}"))
    kb.add(InlineKeyboardButton("❌ Отменить", callback_data="delivery_cancel"))
    return kb


def confirm_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_track"),
        InlineKeyboardButton("❌ Отменить", callback_data="confirm_cancel"),
    )
    return kb


def format_tracks(tracks: List[Tuple[str, Optional[str]]]) -> str:
    if not tracks:
        return "Нет зарегистрированных трек-кодов"
    lines: List[str] = []
    for idx, (track, delivery) in enumerate(tracks, start=1):
        suffix = f" ({delivery})" if delivery else ""
        lines.append(f"{idx}. <code>{track}</code>{suffix}")
    return "\n".join(lines)


def is_valid_track_number(text: str) -> bool:
    t = (text or "").strip().upper()
    if len(t) < 8 or len(t) > 40:
        return False
    return all("A" <= c <= "Z" or "0" <= c <= "9" for c in t)


# Команды и меню

@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    welcome = (
        f"🇨🇳 <b>Добро пожаловать!</b>\n\n"
        f"🔑 Ваш личный код клиента: <code>{code}</code>\n\n"
        f"Выберите действие из меню ниже."
    )
    await message.answer(welcome, parse_mode="HTML", reply_markup=get_main_menu())
    await message.answer("✅ Команда выполнена.")


@dp.message_handler(lambda m: m.text == "🔑 Получить код", state="*")
@dp.message_handler(commands=["getcod"], state="*")
async def cmd_getcod(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    await message.answer(f"🔑 Ваш личный код клиента: <code>{code}</code>", parse_mode="HTML", reply_markup=get_main_menu())
    await message.answer("✅ Команда выполнена.")


@dp.message_handler(lambda m: m.text == "📍 Получить адрес", state="*")
@dp.message_handler(commands=["adress"], state="*")
async def cmd_address(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    await message.answer(CHINA_WAREHOUSE_ADDRESS.format(client_code=code), parse_mode="HTML", reply_markup=get_main_menu())
    await message.answer("✅ Команда выполнена.")


@dp.message_handler(lambda m: m.text == "📦 Мои треки", state="*")
@dp.message_handler(commands=["mycod"], state="*")
async def cmd_mycod(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    tracks = get_tracks(message.from_user.id)
    text = f"🔑 Ваш код клиента: <code>{code}</code>\n\n" + ("📦 Ваши трек-коды:\n\n" + format_tracks(tracks) if tracks else "Пока нет зарегистрированных трек-кодов")
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu())
    await message.answer("✅ Команда выполнена.")


@dp.message_handler(lambda m: m.text == "👨‍💼 Менеджер", state="*")
@dp.message_handler(commands=["manager"], state="*")
async def cmd_manager(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    full_name = message.from_user.full_name or ""
    username = f"@{message.from_user.username}" if message.from_user.username else "не указан"
    if MANAGER_ID:
        try:
            text = (
                "📞 <b>КЛИЕНТ ХОЧЕТ СВЯЗАТЬСЯ С МЕНЕДЖЕРОМ</b>\n\n"
                f"🆔 Код клиента: <code>{code}</code>\n"
                f"👤 Имя: {full_name}\n"
                f"📱 Username: {username}\n"
                f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n"
            )
            await bot.send_message(MANAGER_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify manager: %s", e)
    await message.answer("✅ Сообщение менеджеру отправлено. Ожидайте контакт.", reply_markup=get_main_menu())


@dp.message_handler(lambda m: m.text == "🛒 Заказать", state="*")
@dp.message_handler(commands=["buy"], state="*")
async def cmd_buy(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "🛒 Что вы хотите заказать и в каком количестве? Опишите в следующем сообщении. Для отмены — /cancel",
        reply_markup=get_main_menu(),
    )
    await BuyStates.waiting_for_details.set()


@dp.message_handler(state=BuyStates.waiting_for_details, content_types=[ContentType.TEXT, ContentType.PHOTO])
async def handle_buy_details(message: types.Message, state: FSMContext):
    text = message.caption or message.text or ""
    if len(text.strip()) < 3:
        await message.answer("⚠️ Сообщение слишком короткое. Опишите заказ подробнее или /cancel")
        return
    code = get_or_create_user_code(message.from_user.id)
    full_name = message.from_user.full_name or ""
    username = f"@{message.from_user.username}" if message.from_user.username else "не указан"
    notify = (
        "🛒 <b>НОВЫЙ ЗАПРОС НА ПОКУПКУ</b>\n\n"
        f"🆔 Код клиента: <code>{code}</code>\n"
        f"👤 Имя: {full_name}\n"
        f"📱 Username: {username}\n"
        f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n\n"
        f"📝 Сообщение клиента:\n{text}"
    )
    if MANAGER_ID:
        try:
            if message.photo:
                await bot.send_photo(MANAGER_ID, message.photo[-1].file_id, caption=notify, parse_mode="HTML")
            else:
                await bot.send_message(MANAGER_ID, notify, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify manager: %s", e)
    await state.finish()
    await message.answer("✅ Ваш запрос отправлен менеджеру. Он свяжется с вами.", reply_markup=get_main_menu())


@dp.message_handler(lambda m: m.text == "🚚 Отправить трек", state="*")
@dp.message_handler(commands=["sendtrack"], state="*")
async def cmd_sendtrack(message: types.Message, state: FSMContext):
    await state.finish()
    get_or_create_user_code(message.from_user.id)
    tracks = get_tracks(message.from_user.id)
    if tracks:
        await message.answer("📦 Ваша история зарегистрированных трек-кодов:\n\n" + format_tracks(tracks), parse_mode="HTML")
    await message.answer("📝 Отправьте трек-код одним сообщением. Для отмены — /cancel")
    await TrackStates.waiting_for_track.set()


@dp.message_handler(commands=["cancel"], state="*")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("❌ Действие отменено.", reply_markup=get_main_menu())


# Ввод трека → выбор доставки
@dp.message_handler(state=TrackStates.waiting_for_track, content_types=ContentType.TEXT)
async def handle_track_input(message: types.Message, state: FSMContext):
    track = (message.text or "").strip().upper()
    if not is_valid_track_number(track):
        await message.answer("⚠️ Неверный формат трек-кода. Пришлите другой или /cancel")
        return
    await state.update_data(track=track)
    await TrackStates.choosing_delivery.set()
    await message.answer(
        f"✅ Трек-код принят: <code>{track}</code>\n\nВыберите тип доставки:",
        parse_mode="HTML",
        reply_markup=delivery_keyboard(),
    )


# Выбор доставки → подтверждение
@dp.callback_query_handler(lambda c: c.data.startswith("delivery_"), state=TrackStates.choosing_delivery)
async def choose_delivery(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    if callback.data == "delivery_cancel":
        await state.finish()
        await callback.message.edit_text("❌ Добавление трека отменено")
        await callback.message.answer("Возврат в меню.", reply_markup=get_main_menu())
        return

    delivery_key = callback.data.replace("delivery_", "")
    delivery_name = DELIVERY_TYPES.get(delivery_key, {}).get("name", "Не указано")
    await state.update_data(delivery=delivery_key)

    state_data = await state.get_data()
    track = state_data["track"]

    await TrackStates.confirming.set()
    await callback.message.edit_text(
        f"📦 Трек: <code>{track}</code>\n"
        f"🚚 Доставка: {delivery_name}\n\n"
        f"Подтвердить регистрацию?",
        parse_mode="HTML",
        reply_markup=confirm_keyboard(),
    )


# Подтверждение регистрации
@dp.callback_query_handler(lambda c: c.data in ("confirm_track", "confirm_cancel"), state=TrackStates.confirming)
async def confirm_track(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    if callback.data == "confirm_cancel":
        await state.finish()
        await callback.message.edit_text("❌ Добавление трека отменено")
        await callback.message.answer("Возврат в меню.", reply_markup=get_main_menu())
        return

    # confirm_track
    data = await state.get_data()
    track = data["track"]
    delivery_key = data["delivery"]
    delivery_name = DELIVERY_TYPES.get(delivery_key, {}).get("name", "Не указано")

    add_track(callback.from_user.id, track, delivery_name)

    # Инфо для склада
    code = get_or_create_user_code(callback.from_user.id)
    tracks = get_tracks(callback.from_user.id)
    full_name = callback.from_user.full_name or ""
    username = f"@{callback.from_user.username}" if callback.from_user.username else "не указан"

    if WAREHOUSE_ID:
        try:
            text = (
                "📦 <b>НОВЫЙ ТРЕК-КОД</b>\n\n"
                f"🆔 Код клиента: <code>{code}</code>\n"
                f"👤 Имя: {full_name}\n"
                f"📱 Username: {username}\n"
                f"🆔 Telegram ID: <code>{callback.from_user.id}</code>\n\n"
                f"📋 Трек: <code>{track}</code>\n"
                f"🚚 Доставка: {delivery_name}\n\n"
                "📚 Все треки пользователя:\n" + format_tracks(tracks)
            )
            await bot.send_message(WAREHOUSE_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify warehouse: %s", e)

    await state.finish()
    await callback.message.edit_text(
        "✅ Трек-код зарегистрирован и передан сотруднику склада.\n\n"
        "📚 История ваших треков обновлена.",
        parse_mode="HTML",
    )
    await callback.message.answer("Готово. Выберите следующее действие:", reply_markup=get_main_menu())


# Фоллбэк
@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Выберите действие из меню ниже.", reply_markup=get_main_menu())


# Жизненный цикл
async def on_startup(dp: Dispatcher):
    init_db()
    try:
        if MANAGER_ID:
            await bot.send_message(MANAGER_ID, "🤖 Бот запущен")
    except Exception:
        pass


async def on_shutdown(dp: Dispatcher):
    try:
        if MANAGER_ID:
            await bot.send_message(MANAGER_ID, "🔴 Бот остановлен")
    except Exception:
        pass


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
Меню с кнопками добавлено: Заказать, Менеджер, Получить код, Получить адрес, Отправить трек, Мои треки.
После ввода трека: выбор типа доставки (быстрое авто, медленное авто, ЖД, авиа) и подтверждение регистрации.
а как мне убрать то меню в левой нижней части 
Thought for 14s
Можно. Это «клавиатура» (ReplyKeyboard). Есть 3 простых способа.

Спрятать прямо сейчас
В начале файла добавь импорт:
from aiogram.types import ReplyKeyboardRemove
Там, где ты отправляешь сообщение и хочешь убрать клавиатуру:
await message.answer("Готово, меню скрыто.", reply_markup=ReplyKeyboardRemove())
Всегда без нижнего меню
Убери параметр reply_markup=get_main_menu() из всех message.answer(...).
В обработчике /start тоже не передавай get_main_menu(), а для верности сразу спрячь:
await message.answer("Добро пожаловать!", reply_markup=ReplyKeyboardRemove())
Дальше используй только inline‑кнопки (мы их уже используем для выбора доставки).
Сделать команду для скрытия
Добавь хэндлер:
@dp.message_handler(commands=["hide"])
async def cmd_hide(message: types.Message):
    from aiogram.types import ReplyKeyboardRemove
    await message.answer("Меню скрыто.", reply_markup=ReplyKeyboardRemove())
Когда нужно — напиши боту /hide.
Дополнительно (если мешает «кнопка Меню» с командами /start, /help):

Это отдельный список команд Telegram. Его можно очистить:
from aiogram.types import BotCommand
await bot.set_my_commands([])  # убрать пункты из системного меню
Итого:

Чтобы убрать именно нашу нижнюю клавиатуру — используем ReplyKeyboardRemove.
Чтобы вообще не было нижнего меню — не передаём get_main_menu() и один раз спрячем клавиатуру.
Inline‑кнопки (под сообщением) продолжат работать.
я хочу оставить inline меню, интерактивное меню, а убрать именно системную кнопку меню которая выдвигает шторку с командами и названиями команд 
Thought for 13s
Коротко: полностью скрыть системную кнопку “Меню” нельзя, но можно сделать её пустой. Для этого нужно удалить список команд у бота.

Сделай оба шага:

В коде, на старте бота, очисти команды:
from aiogram.types import (
    BotCommandScopeDefault,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
)

async def on_startup(dp):
    init_db()
    for scope in [
        BotCommandScopeDefault(),
        BotCommandScopeAllPrivateChats(),
        BotCommandScopeAllGroupChats(),
        BotCommandScopeAllChatAdministrators(),
    ]:
        try:
            await bot.delete_my_commands(scope=scope)
        except Exception:
            pass
    # ... остальное что у тебя уже есть
В @BotFather удали команды:
Отправь: /deletecommands
Выбери своего бота
Выбери “Default” (и при необходимости другие scope/языки)
Подтверди удаление
После этого системная “шторка” с командами будет пустой. Inline‑кнопки в сообщениях продолжат работать как раньше.

выдай готовый код 
Thought for 22s
# bot.py
import os
import logging
from typing import List, Optional, Tuple

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    ContentType,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from database import init_db, get_or_create_user_code, get_tracks, add_track


# Логи
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("china_warehouse_bot")
logger.info("RUNNING FILE: %s", os.path.abspath(__file__))


# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
MANAGER_ID = int(os.getenv("MANAGER_ID", "7095008192") or 7095008192)
WAREHOUSE_ID = int(os.getenv("WAREHOUSE_ID", "7095008192") or 7095008192)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


# Плейсхолдер адреса склада — замените этот текст на реальный адрес
CHINA_WAREHOUSE_ADDRESS = (
    "🏭 <b>АДРЕС СКЛАДА В КИТАЕ</b>\n\n"
    "⬇️ ВСТАВЬТЕ НИЖЕ ВАШ РЕАЛЬНЫЙ АДРЕС СКЛАДА (замените этот текст) ⬇️\n"
    "<i>Пример формата: Китай, провинция ..., г. ..., район ..., ул. ..., склад №...</i>\n\n"
    "🔑 <b>ВАШ ЛИЧНЫЙ КОД КЛИЕНТА:</b> <code>{client_code}</code>\n"
)


# Бот
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


# Состояния
class TrackStates(StatesGroup):
    waiting_for_track = State()
    choosing_delivery = State()
    confirming = State()


class BuyStates(StatesGroup):
    waiting_for_details = State()


# Инлайн-меню
def get_main_menu_inline() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🛒 Заказать", callback_data="menu_buy"),
        InlineKeyboardButton("👨‍💼 Менеджер", callback_data="menu_manager"),
    )
    kb.add(
        InlineKeyboardButton("🔑 Получить код", callback_data="menu_getcod"),
        InlineKeyboardButton("📍 Получить адрес", callback_data="menu_address"),
    )
    kb.add(
        InlineKeyboardButton("🚚 Отправить трек", callback_data="menu_sendtrack"),
        InlineKeyboardButton("📦 Мои треки", callback_data="menu_mytracks"),
    )
    return kb


# Варианты доставки (инлайн)
DELIVERY_TYPES = {
    "fast_auto": {"name": "🚛 Быстрое авто"},
    "slow_auto": {"name": "🚚 Медленное авто"},
    "rail": {"name": "🚂 ЖД"},
    "air": {"name": "✈️ Авиа"},
}


def delivery_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for key, info in DELIVERY_TYPES.items():
        kb.add(InlineKeyboardButton(info["name"], callback_data=f"delivery_{key}"))
    kb.add(InlineKeyboardButton("❌ Отменить", callback_data="delivery_cancel"))
    return kb


def confirm_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_track"),
        InlineKeyboardButton("❌ Отменить", callback_data="confirm_cancel"),
    )
    return kb


def format_tracks(tracks: List[Tuple[str, Optional[str]]]) -> str:
    if not tracks:
        return "Нет зарегистрированных трек-кодов"
    lines: List[str] = []
    for idx, (track, delivery) in enumerate(tracks, start=1):
        suffix = f" ({delivery})" if delivery else ""
        lines.append(f"{idx}. <code>{track}</code>{suffix}")
    return "\n".join(lines)


def is_valid_track_number(text: str) -> bool:
    t = (text or "").strip().upper()
    if len(t) < 8 or len(t) > 40:
        return False
    return all("A" <= c <= "Z" or "0" <= c <= "9" for c in t)


# Хелперы действий
async def action_get_code(message: types.Message):
    code = get_or_create_user_code(message.from_user.id)
    await message.answer(f"🔑 Ваш личный код клиента: <code>{code}</code>", parse_mode="HTML")


async def action_get_address(message: types.Message):
    code = get_or_create_user_code(message.from_user.id)
    await message.answer(CHINA_WAREHOUSE_ADDRESS.format(client_code=code), parse_mode="HTML")


async def action_my_tracks(message: types.Message):
    code = get_or_create_user_code(message.from_user.id)
    tracks = get_tracks(message.from_user.id)
    text = f"🔑 Ваш код клиента: <code>{code}</code>\n\n"
    text += "📦 Ваши трек-коды:\n\n" + format_tracks(tracks) if tracks else "Пока нет зарегистрированных трек-кодов"
    await message.answer(text, parse_mode="HTML")


async def action_manager(message: types.Message):
    code = get_or_create_user_code(message.from_user.id)
    full_name = message.from_user.full_name or ""
    username = f"@{message.from_user.username}" if message.from_user.username else "не указан"
    if MANAGER_ID:
        try:
            text = (
                "📞 <b>КЛИЕНТ ХОЧЕТ СВЯЗАТЬСЯ С МЕНЕДЖЕРОМ</b>\n\n"
                f"🆔 Код клиента: <code>{code}</code>\n"
                f"👤 Имя: {full_name}\n"
                f"📱 Username: {username}\n"
                f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n"
            )
            await bot.send_message(MANAGER_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify manager: %s", e)
    await message.answer("✅ Сообщение менеджеру отправлено. Ожидайте контакт.")


# Команды и меню

@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    code = get_or_create_user_code(message.from_user.id)
    welcome = (
        f"🇨🇳 <b>Добро пожаловать!</b>\n\n"
        f"🔑 Ваш личный код клиента: <code>{code}</code>\n\n"
        f"Выберите действие:"
    )
    await message.answer(welcome, parse_mode="HTML", reply_markup=get_main_menu_inline())
    await message.answer("✅ Команда выполнена.")


# Инлайн-меню колбэки
@dp.callback_query_handler(lambda c: c.data == "menu_getcod", state="*")
async def menu_getcod(cb: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(cb.id)
    await action_get_code(cb.message)
    await cb.message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_address", state="*")
async def menu_address(cb: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(cb.id)
    await action_get_address(cb.message)
    await cb.message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_mytracks", state="*")
async def menu_mytracks(cb: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(cb.id)
    await action_my_tracks(cb.message)
    await cb.message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_manager", state="*")
async def menu_manager(cb: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(cb.id)
    await action_manager(cb.message)
    await cb.message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_buy", state="*")
async def menu_buy(cb: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(cb.id)
    await state.finish()
    await cb.message.answer(
        "🛒 Что вы хотите заказать и в каком количестве? Ответьте одним сообщением.\nДля отмены — /cancel"
    )
    await BuyStates.waiting_for_details.set()


@dp.message_handler(state=BuyStates.waiting_for_details, content_types=[ContentType.TEXT, ContentType.PHOTO])
async def handle_buy_details(message: types.Message, state: FSMContext):
    text = message.caption or message.text or ""
    if len(text.strip()) < 3:
        await message.answer("⚠️ Сообщение слишком короткое. Опишите заказ подробнее или /cancel")
        return
    code = get_or_create_user_code(message.from_user.id)
    full_name = message.from_user.full_name or ""
    username = f"@{message.from_user.username}" if message.from_user.username else "не указан"
    notify = (
        "🛒 <b>НОВЫЙ ЗАПРОС НА ПОКУПКУ</b>\n\n"
        f"🆔 Код клиента: <code>{code}</code>\n"
        f"👤 Имя: {full_name}\n"
        f"📱 Username: {username}\n"
        f"🆔 Telegram ID: <code>{message.from_user.id}</code>\n\n"
        f"📝 Сообщение клиента:\n{text}"
    )
    if MANAGER_ID:
        try:
            if message.photo:
                await bot.send_photo(MANAGER_ID, message.photo[-1].file_id, caption=notify, parse_mode="HTML")
            else:
                await bot.send_message(MANAGER_ID, notify, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify manager: %s", e)
    await state.finish()
    await message.answer("✅ Ваш запрос отправлен менеджеру. Он свяжется с вами.")
    await message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_sendtrack", state="*")
async def menu_sendtrack(cb: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(cb.id)
    await state.finish()
    get_or_create_user_code(cb.from_user.id)
    tracks = get_tracks(cb.from_user.id)
    if tracks:
        await cb.message.answer("📦 Ваша история зарегистрированных трек-кодов:\n\n" + format_tracks(tracks), parse_mode="HTML")
    await cb.message.answer("📝 Отправьте трек-код одним сообщением. Для отмены — /cancel")
    await TrackStates.waiting_for_track.set()


@dp.message_handler(commands=["cancel"], state="*")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("❌ Действие отменено.")
    await message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


# Ввод трека → выбор доставки
@dp.message_handler(state=TrackStates.waiting_for_track, content_types=ContentType.TEXT)
async def handle_track_input(message: types.Message, state: FSMContext):
    track = (message.text or "").strip().upper()
    if not is_valid_track_number(track):
        await message.answer("⚠️ Неверный формат трек-кода. Пришлите другой или /cancel")
        return
    await state.update_data(track=track)
    await TrackStates.choosing_delivery.set()
    await message.answer(
        f"✅ Трек-код принят: <code>{track}</code>\n\nВыберите тип доставки:",
        parse_mode="HTML",
        reply_markup=delivery_keyboard(),
    )


# Выбор доставки → подтверждение
@dp.callback_query_handler(lambda c: c.data.startswith("delivery_"), state=TrackStates.choosing_delivery)
async def choose_delivery(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    if callback.data == "delivery_cancel":
        await state.finish()
        await callback.message.edit_text("❌ Добавление трека отменено")
        await callback.message.answer("Выберите действие:", reply_markup=get_main_menu_inline())
        return

    delivery_key = callback.data.replace("delivery_", "")
    delivery_name = DELIVERY_TYPES.get(delivery_key, {}).get("name", "Не указано")
    await state.update_data(delivery=delivery_key)

    data = await state.get_data()
    track = data["track"]

    await TrackStates.confirming.set()
    await callback.message.edit_text(
        f"📦 Трек: <code>{track}</code>\n"
        f"🚚 Доставка: {delivery_name}\n\n"
        f"Подтвердить регистрацию?",
        parse_mode="HTML",
        reply_markup=confirm_keyboard(),
    )


# Подтверждение регистрации
@dp.callback_query_handler(lambda c: c.data in ("confirm_track", "confirm_cancel"), state=TrackStates.confirming)
async def confirm_track(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    if callback.data == "confirm_cancel":
        await state.finish()
        await callback.message.edit_text("❌ Добавление трека отменено")
        await callback.message.answer("Выберите действие:", reply_markup=get_main_menu_inline())
        return

    data = await state.get_data()
    track = data["track"]
    delivery_key = data["delivery"]
    delivery_name = DELIVERY_TYPES.get(delivery_key, {}).get("name", "Не указано")

    add_track(callback.from_user.id, track, delivery_name)

    code = get_or_create_user_code(callback.from_user.id)
    tracks = get_tracks(callback.from_user.id)
    full_name = callback.from_user.full_name or ""
    username = f"@{callback.from_user.username}" if callback.from_user.username else "не указан"

    if WAREHOUSE_ID:
        try:
            text = (
                "📦 <b>НОВЫЙ ТРЕК-КОД</b>\n\n"
                f"🆔 Код клиента: <code>{code}</code>\n"
                f"👤 Имя: {full_name}\n"
                f"📱 Username: {username}\n"
                f"🆔 Telegram ID: <code>{callback.from_user.id}</code>\n\n"
                f"📋 Трек: <code>{track}</code>\n"
                f"🚚 Доставка: {delivery_name}\n\n"
                "📚 Все треки пользователя:\n" + format_tracks(tracks)
            )
            await bot.send_message(WAREHOUSE_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify warehouse: %s", e)

    await state.finish()
    await callback.message.edit_text(
        "✅ Трек-код зарегистрирован и передан сотруднику склада.\n\n"
        "📚 История ваших треков обновлена.",
        parse_mode="HTML",
    )
    await callback.message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


# Фоллбэк
@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


# Жизненный цикл (очистка системного меню команд)
async def on_startup(dp: Dispatcher):
    init_db()
    # Удаляем системное меню команд (чтобы не было «шторки» команд)
    try:
        from aiogram.types import (
            BotCommandScopeDefault,
            BotCommandScopeAllPrivateChats,
            BotCommandScopeAllGroupChats,
            BotCommandScopeAllChatAdministrators,
        )
        for scope in [
            BotCommandScopeDefault(),
            BotCommandScopeAllPrivateChats(),
            BotCommandScopeAllGroupChats(),
            BotCommandScopeAllChatAdministrators(),
        ]:
            try:
                await bot.delete_my_commands(scope=scope)
            except Exception:
                pass
        # На всякий случай удалим команды без указания scope
        try:
            await bot.delete_my_commands()
        except Exception:
            pass
    except Exception:
        # Если типы scope недоступны — удалим команды по умолчанию
        try:
            await bot.delete_my_commands()
        except Exception:
            pass

    # Уведомление о запуске (необязательно)
    try:
        if MANAGER_ID:
            await bot.send_message(MANAGER_ID, "🤖 Бот запущен")
    except Exception:
        pass


async def on_shutdown(dp: Dispatcher):
    try:
        if MANAGER_ID:
            await bot.send_message(MANAGER_ID, "🔴 Бот остановлен")
    except Exception:
        pass


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
