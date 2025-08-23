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
