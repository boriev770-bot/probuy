import os
import logging
import re
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

from database import (
    init_db,
    get_user_code,
    get_or_create_user_code,
    get_tracks,
    add_track,
    add_track_photo,
    get_track_photos,
    find_user_ids_by_track,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("china_warehouse_bot")
logger.info("RUNNING FILE: %s", os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN")
MANAGER_ID = int(os.getenv("MANAGER_ID", "7095008192") or 7095008192)
WAREHOUSE_ID = int(os.getenv("WAREHOUSE_ID", "7095008192") or 7095008192)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

CHINA_WAREHOUSE_ADDRESS = (
    "🏭 <b>АДРЕС СКЛАДА В КИТАЕ</b>\n\n"
    "⬇️ ВСТАВЬТЕ НИЖЕ ВАШ РЕАЛЬНЫЙ АДРЕС СКЛАДА (замените этот текст) ⬇️\n"
    "<i>Пример формата: Китай, провинция ..., г. ..., район ..., ул. ..., склад №...</i>\n\n"
    "🔑 <b>ВАШ ЛИЧНЫЙ КОД КЛИЕНТА:</b> <code>{client_code}</code>\n"
)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class TrackStates(StatesGroup):
    waiting_for_track = State()
    choosing_delivery = State()
    confirming = State()


class BuyStates(StatesGroup):
    waiting_for_details = State()


class PhotoStates(StatesGroup):
    waiting_for_track = State()


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
    kb.add(
        InlineKeyboardButton("📷 Фотоконтроль", callback_data="menu_photokontrol"),
    )
    return kb


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


def extract_track_from_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    text_upper = text.upper()
    # Ищем подходящую последовательность символов A-Z0-9 длиной 8..40
    match = re.search(r"[A-Z0-9]{8,40}", text_upper)
    if match:
        candidate = match.group(0)
        return candidate if is_valid_track_number(candidate) else None
    return None


async def require_code_or_hint(message: types.Message) -> Optional[str]:
    code = get_user_code(message.from_user.id)
    if not code:
        await message.answer("Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
        return None
    return code


@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    welcome = (
        "🇨🇳 <b>Добро пожаловать!</b>\n\n"
        "Нажмите «🔑 Получить код», чтобы создать ваш личный код клиента.\n"
        "Затем используйте остальные функции в меню."
    )
    await message.answer(welcome, parse_mode="HTML", reply_markup=get_main_menu_inline())
    await message.answer("✅ Команда выполнена.")


@dp.callback_query_handler(lambda c: c.data == "menu_getcod", state="*")
@dp.message_handler(commands=["getcod"], state="*")
async def menu_getcod(cb_or_msg, state: FSMContext):
    await state.finish()
    if isinstance(cb_or_msg, CallbackQuery):
        await bot.answer_callback_query(cb_or_msg.id)
        tgt = cb_or_msg.message
        user_id = cb_or_msg.from_user.id
    else:
        tgt = cb_or_msg
        user_id = cb_or_msg.from_user.id

    code = get_user_code(user_id)
    if not code:
        code = get_or_create_user_code(user_id)

    await tgt.answer(f"🔑 Ваш личный код клиента: <code>{code}</code>", parse_mode="HTML")
    await tgt.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_address", state="*")
@dp.message_handler(commands=["adress"], state="*")
async def menu_address(cb_or_msg, state: FSMContext):
    await state.finish()
    if isinstance(cb_or_msg, CallbackQuery):
        await bot.answer_callback_query(cb_or_msg.id)
        tgt = cb_or_msg.message
        user_id = cb_or_msg.from_user.id
    else:
        tgt = cb_or_msg
        user_id = cb_or_msg.from_user.id

    code = get_user_code(user_id)
    if not code:
        await tgt.answer("Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
        return

    await tgt.answer(CHINA_WAREHOUSE_ADDRESS.format(client_code=code), parse_mode="HTML")
    await tgt.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_mytracks", state="*")
@dp.message_handler(commands=["mycod"], state="*")
async def menu_mytracks(cb_or_msg, state: FSMContext):
    await state.finish()
    if isinstance(cb_or_msg, CallbackQuery):
        await bot.answer_callback_query(cb_or_msg.id)
        tgt = cb_or_msg.message
        user_id = cb_or_msg.from_user.id
    else:
        tgt = cb_or_msg
        user_id = cb_or_msg.from_user.id

    code = get_user_code(user_id)
    if not code:
        await tgt.answer("Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
        return

    tracks = get_tracks(user_id)
    text = f"🔑 Ваш код клиента: <code>{code}</code>\n\n" + ("📦 Ваши трек-коды:\n\n" + format_tracks(tracks) if tracks else "Пока нет зарегистрированных трек-кодов")
    await tgt.answer(text, parse_mode="HTML")
    await tgt.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_manager", state="*")
@dp.message_handler(commands=["manager"], state="*")
async def menu_manager(cb_or_msg, state: FSMContext):
    await state.finish()
    if isinstance(cb_or_msg, CallbackQuery):
        await bot.answer_callback_query(cb_or_msg.id)
        tgt = cb_or_msg.message
        user = cb_or_msg.from_user
    else:
        tgt = cb_or_msg
        user = cb_or_msg.from_user

    code = get_user_code(user.id)
    if not code:
        await tgt.answer("Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
        return

    full_name = user.full_name or ""
    username = f"@{user.username}" if user.username else "не указан"
    if MANAGER_ID:
        try:
            text = (
                "📞 <b>КЛИЕНТ ХОЧЕТ СВЯЗАТЬСЯ С МЕНЕДЖЕРОМ</b>\n\n"
                f"🆔 Код клиента: <code>{code}</code>\n"
                f"👤 Имя: {full_name}\n"
                f"📱 Username: {username}\n"
                f"🆔 Telegram ID: <code>{user.id}</code>\n"
            )
            await bot.send_message(MANAGER_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify manager: %s", e)
    await tgt.answer("✅ Сообщение менеджеру отправлено. Ожидайте контакт.", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_buy", state="*")
@dp.message_handler(commands=["buy"], state="*")
async def menu_buy(cb_or_msg, state: FSMContext):
    await state.finish()
    if isinstance(cb_or_msg, CallbackQuery):
        await bot.answer_callback_query(cb_or_msg.id)
        tgt = cb_or_msg.message
        user_id = cb_or_msg.from_user.id
    else:
        tgt = cb_or_msg
        user_id = cb_or_msg.from_user.id

    code = get_user_code(user_id)
    if not code:
        await tgt.answer("Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
        return

    await tgt.answer("🛒 Что вы хотите заказать и в каком количестве? Ответьте одним сообщением.\nДля отмены — /cancel")
    await BuyStates.waiting_for_details.set()


@dp.message_handler(state=BuyStates.waiting_for_details, content_types=[ContentType.TEXT, ContentType.PHOTO])
async def handle_buy_details(message: types.Message, state: FSMContext):
    code = await require_code_or_hint(message)
    if not code:
        await state.finish()
        return

    text = message.caption or message.text or ""
    if len(text.strip()) < 3:
        await message.answer("⚠️ Сообщение слишком короткое. Опишите заказ подробнее или /cancel")
        return

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
@dp.message_handler(commands=["sendtrack"], state="*")
async def menu_sendtrack(cb_or_msg, state: FSMContext):
    await state.finish()
    if isinstance(cb_or_msg, CallbackQuery):
        await bot.answer_callback_query(cb_or_msg.id)
        tgt = cb_or_msg.message
        user_id = cb_or_msg.from_user.id
    else:
        tgt = cb_or_msg
        user_id = cb_or_msg.from_user.id

    code = get_user_code(user_id)
    if not code:
        await tgt.answer("Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
        return

    tracks = get_tracks(user_id)
    if tracks:
        await tgt.answer("📦 Ваша история зарегистрированных трек-кодов:\n\n" + format_tracks(tracks), parse_mode="HTML")
    await tgt.answer("📝 Отправьте трек-код одним сообщением. Для отмены — /cancel")
    await TrackStates.waiting_for_track.set()


@dp.message_handler(commands=["cancel"], state="*")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("❌ Действие отменено.")
    await message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.message_handler(state=TrackStates.waiting_for_track, content_types=ContentType.TEXT)
async def handle_track_input(message: types.Message, state: FSMContext):
    code = await require_code_or_hint(message)
    if not code:
        await state.finish()
        return

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


@dp.callback_query_handler(lambda c: c.data in ("confirm_track", "confirm_cancel"), state=TrackStates.confirming)
async def confirm_track(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    if callback.data == "confirm_cancel":
        await state.finish()
        await callback.message.edit_text("❌ Добавление трека отменено")
        await callback.message.answer("Выберите действие:", reply_markup=get_main_menu_inline())
        return

    user_id = callback.from_user.id
    code = get_user_code(user_id)
    if not code:
        await state.finish()
        await callback.message.edit_text("Сначала получите личный код: нажмите «🔑 Получить код».")
        await callback.message.answer("Выберите действие:", reply_markup=get_main_menu_inline())
        return

    data = await state.get_data()
    track = data["track"]
    delivery_key = data["delivery"]
    delivery_name = DELIVERY_TYPES.get(delivery_key, {}).get("name", "Не указано")

    add_track(user_id, track, delivery_name)

    tracks = get_tracks(user_id)
    full_name = callback.from_user.full_name or ""
    username = f"@{callback.from_user.username}" if callback.from_user.username else "не указан"

    if WAREHOUSE_ID:
        try:
            text = (
                "📦 <b>НОВЫЙ ТРЕК-КОД</b>\n\n"
                f"🆔 Код клиента: <code>{code}</code>\n"
                f"👤 Имя: {full_name}\n"
                f"📱 Username: {username}\n"
                f"🆔 Telegram ID: <code>{user_id}</code>\n\n"
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


@dp.callback_query_handler(lambda c: c.data == "menu_photokontrol", state="*")
@dp.message_handler(commands=["photo", "photos"], state="*")
async def menu_photokontrol(cb_or_msg, state: FSMContext):
    await state.finish()
    if isinstance(cb_or_msg, CallbackQuery):
        await bot.answer_callback_query(cb_or_msg.id)
        tgt = cb_or_msg.message
        user_id = cb_or_msg.from_user.id
    else:
        tgt = cb_or_msg
        user_id = cb_or_msg.from_user.id

    code = get_user_code(user_id)
    if not code:
        await tgt.answer("Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
        return

    user_tracks = get_tracks(user_id)
    if user_tracks:
        await tgt.answer("📦 Ваши треки:\n\n" + format_tracks(user_tracks), parse_mode="HTML")
    await tgt.answer("📷 Отправьте трек-код, чтобы получить фото. Для отмены — /cancel")
    await PhotoStates.waiting_for_track.set()


@dp.message_handler(state=PhotoStates.waiting_for_track, content_types=ContentType.TEXT)
async def handle_photo_request(message: types.Message, state: FSMContext):
    code = await require_code_or_hint(message)
    if not code:
        await state.finish()
        return

    track = (message.text or "").strip().upper()
    if not is_valid_track_number(track):
        await message.answer("⚠️ Неверный формат трек-кода. Пришлите другой или /cancel")
        return

    photos = get_track_photos(track)
    if not photos:
        await state.finish()
        await message.answer(
            f"📭 Фото по треку <code>{track}</code> пока не загружены.",
            parse_mode="HTML",
        )
        await message.answer("Выберите действие:", reply_markup=get_main_menu_inline())
        return

    # Отправляем все фото пользователю
    first = True
    for file_id in photos:
        try:
            caption = f"📷 Фото по треку: <code>{track}</code>" if first else None
            await bot.send_photo(message.chat.id, file_id, caption=caption, parse_mode="HTML")
            first = False
        except Exception as e:
            logger.exception("Failed to send track photo to user: %s", e)

    await state.finish()
    await message.answer("✅ Все доступные фото отправлены.")
    await message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


@dp.message_handler(content_types=[ContentType.PHOTO], state="*")
async def warehouse_photo_upload(message: types.Message, state: FSMContext):
    # Обрабатываем фото только от аккаунта склада
    if message.from_user.id != WAREHOUSE_ID:
        return

    # Пытаемся извлечь трек из подписи к фото или из реплая
    track = extract_track_from_text(message.caption)
    if not track and message.reply_to_message:
        # Пытаемся из текста или подписи исходного сообщения
        track = extract_track_from_text(getattr(message.reply_to_message, "text", None) or getattr(message.reply_to_message, "caption", None))

    if not track:
        await message.answer(
            "⚠️ Не удалось распознать трек-код. Укажите трек в подписи (например: AB123456789CN) или отправьте фото ответом на сообщение с треком."
        )
        return

    track = track.upper()
    file_id = message.photo[-1].file_id

    try:
        add_track_photo(track, file_id, uploaded_by=message.from_user.id, caption=message.caption)
    except Exception as e:
        logger.exception("Failed to save track photo: %s", e)
        await message.answer("❌ Ошибка сохранения фото. Попробуйте позже.")
        return

    # Ищем пользователей, у кого зарегистрирован этот трек
    user_ids = find_user_ids_by_track(track)
    sent_count = 0
    for uid in set(user_ids):
        try:
            await bot.send_photo(uid, file_id, caption=f"📷 Фото по треку: <code>{track}</code>", parse_mode="HTML")
            sent_count += 1
        except Exception as e:
            logger.exception("Failed to deliver track photo to user %s: %s", uid, e)

    if sent_count > 0:
        await message.answer(f"✅ Фото сохранено и отправлено {sent_count} клиенту(ам).")
    else:
        await message.answer(
            "ℹ️ Фото сохранено. Клиенты по этому треку не найдены. Как только клиент зарегистрирует трек, он сможет увидеть фото."
        )


@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=get_main_menu_inline())


async def on_startup(dp: Dispatcher):
    init_db()
    try:
        # Чистим системное меню команд
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
        try:
            await bot.delete_my_commands()
        except Exception:
            pass
    except Exception:
        pass

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
