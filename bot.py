import os
import asyncio
import logging
import re
from typing import List, Optional, Tuple

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
	ContentType,
	InlineKeyboardMarkup,
	InlineKeyboardButton,
	ReplyKeyboardMarkup,
	KeyboardButton,
	CallbackQuery,
    WebAppInfo,
    InputMediaPhoto,
)
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.middlewares import BaseMiddleware

from database import (
	init_db,
	get_user_code,
	get_or_create_user_code,
	get_tracks,
	add_track,
	add_track_photo,
	get_track_photos,
	find_user_ids_by_track,
	delete_all_user_tracks,
    get_user_id_by_code,
    get_recipient,
    set_recipient,
    get_next_cargo_num,
    create_shipment,
    get_user_id_by_cargo_code,
    update_shipment_status,
    list_user_shipments_by_status,
    delete_all_user_shipments,
    count_user_shipments,
	# reminders/activity
	record_user_activity,
	mark_pressed_address,
	mark_pressed_sendcargo,
	get_users_for_address_reminder,
	get_users_for_sendcargo_reminder,
	get_users_for_inactive_reminder,
	mark_address_reminder_sent,
	mark_sendcargo_reminder_sent,
	mark_inactive_reminder_sent,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("china_warehouse_bot")
logger.info("RUNNING FILE: %s", os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN")

def _resolve_webapp_url() -> str:
	# Priority: explicit WEBAPP_URL, then common hosting envs
	candidates = [
		(os.getenv("WEBAPP_URL", "").strip()),
		(os.getenv("PUBLIC_URL", "").strip()),
		(os.getenv("RENDER_EXTERNAL_URL", "").strip()),
		(os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()),
		(os.getenv("VERCEL_URL", "").strip()),
	]
	# Compose from FLY_APP_NAME if others are empty
	fly_name = (os.getenv("FLY_APP_NAME", "").strip())
	if fly_name and not any(candidates):
		candidates.append(f"{fly_name}.fly.dev")
	for url in candidates:
		if not url:
			continue
		if not (url.startswith("http://") or url.startswith("https://")):
			url = f"https://{url}"
		return url
	return ""

WEBAPP_URL = _resolve_webapp_url()
MANAGER_ID = int(os.getenv("MANAGER_ID", "7095008192") or 7095008192)
WAREHOUSE_ID = int(os.getenv("WAREHOUSE_ID", "7095008192") or 7095008192)

if not BOT_TOKEN:
	raise RuntimeError("BOT_TOKEN is not set")

CHINA_WAREHOUSE_ADDRESS = (
	"张生生{client_code}\n"
	"16604524466 \n"
	"广东省 佛山市 南海区 里水镇 东秀路 河塱沙5号 一楼仓库EM00-ХХХХХ"
)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


# Держим одно «экранное» сообщение меню на чат и редактируем его вместо спама новыми сообщениями
_menu_message_by_chat: dict[int, int] = {}


class ActivityMiddleware(BaseMiddleware):
    async def on_pre_process_message(self, message: types.Message, data: dict):
        try:
            if message.from_user:
                record_user_activity(int(message.from_user.id))
        except Exception:
            pass

    async def on_pre_process_callback_query(self, callback_query: CallbackQuery, data: dict):
        try:
            if callback_query.from_user:
                record_user_activity(int(callback_query.from_user.id))
        except Exception:
            pass


async def show_menu_screen(chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, parse_mode: Optional[str] = "HTML") -> None:
	message_id = _menu_message_by_chat.get(chat_id)
	if message_id:
		try:
			await bot.edit_message_text(
				chat_id=chat_id,
				message_id=message_id,
				text=text,
				parse_mode=parse_mode,
				reply_markup=reply_markup,
			)
			return
		except Exception:
			# Если не удалось отредактировать (удалено/устарело) — пришлём новое и запомним id
			pass
	sent = await bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
	_menu_message_by_chat[chat_id] = sent.message_id


class TrackStates(StatesGroup):
	waiting_for_track = State()
	choosing_delivery = State()
	confirming = State()


class BuyStates(StatesGroup):
	waiting_for_details = State()


class PhotoStates(StatesGroup):
	waiting_for_track = State()


class CargoStates(StatesGroup):
	waiting_for_recipient = State()
	choosing_delivery = State()
	confirming = State()


class AdminShipmentStates(StatesGroup):
	waiting_for_cargo_code = State()
	waiting_for_media = State()


# Буфер для медиа-альбомов администратора
_admin_album_buffers: dict[str, list[dict]] = {}


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
		InlineKeyboardButton("🏭 Склад", callback_data="menu_warehouse"),
		InlineKeyboardButton("📦 Статус груза", callback_data="menu_status"),
	)
	kb.add(
		InlineKeyboardButton("📷 Фотоконтроль", callback_data="menu_photokontrol"),
	)
	kb.add(
		InlineKeyboardButton("🧹 Очистить историю", callback_data="menu_clearhistory"),
	)
	return kb


def get_main_menu_reply() -> ReplyKeyboardMarkup:
	kb = ReplyKeyboardMarkup(resize_keyboard=True)
	kb.row(KeyboardButton("🛒 Заказать"), KeyboardButton("👨‍💼 Менеджер"))
	kb.row(KeyboardButton("🔑 Получить код"), KeyboardButton("📍 Получить адрес"))
	kb.row(KeyboardButton("🏭 Склад"), KeyboardButton("📦 Статус груза"))
	kb.row(KeyboardButton("📷 Фотоконтроль"))
	kb.row(KeyboardButton("🧹 Очистить историю"))
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


def clear_history_confirm_keyboard() -> InlineKeyboardMarkup:
	kb = InlineKeyboardMarkup(row_width=2)
	kb.add(
		InlineKeyboardButton("🧹 Очистить", callback_data="clear_confirm"),
		InlineKeyboardButton("❌ Отменить", callback_data="clear_cancel"),
	)
	return kb


def clear_history_entry_keyboard() -> InlineKeyboardMarkup:
	kb = InlineKeyboardMarkup(row_width=1)
	kb.add(InlineKeyboardButton("🧹 Очистить историю", callback_data="menu_clearhistory"))
	return kb


def cargo_confirm_keyboard() -> InlineKeyboardMarkup:
	kb = InlineKeyboardMarkup(row_width=2)
	kb.add(
		InlineKeyboardButton("✅ Подтвердить", callback_data="cargo_confirm"),
		InlineKeyboardButton("✏️ Изменить", callback_data="cargo_edit"),
	)
	kb.add(InlineKeyboardButton("❌ Отменить", callback_data="cargo_cancel"))
	return kb


def warehouse_menu_keyboard() -> InlineKeyboardMarkup:
	kb = InlineKeyboardMarkup(row_width=2)
	kb.add(
		InlineKeyboardButton("🚚 Отправить трек", callback_data="menu_sendtrack"),
		InlineKeyboardButton("📦 Мои треки", callback_data="menu_mytracks"),
	)
	kb.add(
		InlineKeyboardButton("📤 Отправить груз", callback_data="menu_sendcargo"),
	)
	kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_main"))
	return kb


def cargo_status_menu_keyboard() -> InlineKeyboardMarkup:
	kb = InlineKeyboardMarkup(row_width=2)
	kb.add(
		InlineKeyboardButton("🧰 На сборке", callback_data="status_building"),
		InlineKeyboardButton("✅ Отгруженные", callback_data="status_shipped"),
	)
	kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_main"))
	return kb


def parse_recipient_input(text: Optional[str]) -> Optional[Tuple[str, str, str]]:
	if not text:
		return None
	raw = text.strip()
	if not raw:
		return None
	# Разрешаем разделители: ; , или перенос строки
	parts = re.split(r"[;\n,]+", raw)
	parts = [p.strip() for p in parts if p.strip()]
	if len(parts) < 3:
		return None
	fio, phone, city = parts[0], parts[1], parts[2]
	return fio, phone, city


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


def extract_cargo_code(text: Optional[str]) -> Optional[str]:
	if not text:
		return None
	raw = (text or "").strip().upper()
	# Ожидаем полный номер груза: EM03-00001-1
	m = re.search(r"\bEM\d{2}-\d{5}-\d+\b", raw)
	if m:
		return m.group(0)
	# Попытка нормализации: EM03 00001 1 или EM03-00001 1 -> EM03-00001-1
	m = re.search(r"\b(EM\d{2})\D*(\d{5})\D*(\d+)\b", raw)
	if m:
		return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
	return None


async def require_code_or_hint(message: types.Message) -> Optional[str]:
	code = get_user_code(message.from_user.id)
	if not code:
		await show_menu_screen(message.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
		return None
	return code


@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
	await state.finish()
	welcome = (
		"🇨🇳 <b>Добро пожаловать в ProBuy!</b>\n\n"
		"Нажмите «🔑 Получить код», чтобы создать ваш личный код клиента.\n"
		"Затем используйте остальные функции в меню.\n\n"
		"🧹 Поможем заказать товары из Китая и доставить их быстро и выгодно."
	)
	await show_menu_screen(message.chat.id, welcome, reply_markup=get_main_menu_inline(), parse_mode="HTML")


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

	await show_menu_screen(tgt.chat.id, f"🔑 Ваш личный код клиента: <code>{code}</code>", reply_markup=get_main_menu_inline())


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
		await show_menu_screen(tgt.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
		return

	await show_menu_screen(tgt.chat.id, CHINA_WAREHOUSE_ADDRESS.format(client_code=code), reply_markup=get_main_menu_inline(), parse_mode="HTML")
	try:
		mark_pressed_address(int(user_id))
	except Exception:
		pass


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
		await show_menu_screen(tgt.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
		return

	tracks = get_tracks(user_id)
	text = f"🔑 Ваш код клиента: <code>{code}</code>\n\n" + ("📦 Ваши трек-коды:\n\n" + format_tracks(tracks) if tracks else "Пока нет зарегистрированных трек-кодов")
	await show_menu_screen(tgt.chat.id, text, reply_markup=clear_history_entry_keyboard(), parse_mode="HTML")


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
		await show_menu_screen(tgt.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
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
	await show_menu_screen(tgt.chat.id, "✅ Сообщение менеджеру отправлено. Ожидайте контакт.", reply_markup=get_main_menu_inline())


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
		await show_menu_screen(tgt.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
		return

	await show_menu_screen(tgt.chat.id, "🛒 Что вы хотите заказать и в каком количестве? Ответьте одним сообщением.\nДля отмены — /cancel", reply_markup=get_main_menu_inline())
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
	await show_menu_screen(message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())


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
		await show_menu_screen(tgt.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
		return

	tracks = get_tracks(user_id)
	text_parts = []
	if tracks:
		text_parts.append("📦 Ваша история зарегистрированных трек-кодов:\n\n" + format_tracks(tracks))
	text_parts.append("📝 Отправьте трек-код одним сообщением. Для отмены — /cancel")
	text = "\n\n".join(text_parts)
	await show_menu_screen(tgt.chat.id, text, reply_markup=(clear_history_entry_keyboard() if tracks else None), parse_mode=("HTML" if tracks else None))
	await TrackStates.waiting_for_track.set()


@dp.callback_query_handler(lambda c: c.data == "menu_sendcargo", state="*")
async def menu_sendcargo(callback: CallbackQuery, state: FSMContext):
	await bot.answer_callback_query(callback.id)
	await state.finish()
	user_id = callback.from_user.id
	code = get_user_code(user_id)
	if not code:
		await show_menu_screen(callback.message.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
		return

	try:
		mark_pressed_sendcargo(int(user_id))
	except Exception:
		pass

	# Проверим, есть ли сохраненные данные получателя
	saved = get_recipient(user_id)
	if saved and all(saved.get(k) for k in ("fio", "phone", "city")):
		fio, phone, city = saved["fio"], saved["phone"], saved["city"]
		tracks = get_tracks(user_id)
		text = (
			"📤 Заявка на отправку груза\n\n"
			f"🆔 Код клиента: <code>{code}</code>\n"
			f"👤 Получатель: {fio}\n"
			f"📞 Телефон: {phone}\n"
			f"🏙️ Город доставки: {city}\n\n"
			"📚 Зарегистрированные треки:\n" + (format_tracks(tracks) if tracks else "Нет зарегистрированных трек-кодов") + "\n\n"
			"Выберите тип доставки:"
		)
		await state.update_data(fio=fio, phone=phone, city=city)
		await CargoStates.choosing_delivery.set()
		await show_menu_screen(callback.message.chat.id, text, reply_markup=delivery_keyboard(), parse_mode="HTML")
		return

	await show_menu_screen(callback.message.chat.id, "✍️ Пришлите данные получателя одной строкой: ФИО; телефон; город доставки\nНапример: Иванов Иван; +7 999 000-00-00; Москва\nДля отмены — /cancel", reply_markup=get_main_menu_inline())
	await CargoStates.waiting_for_recipient.set()


@dp.message_handler(commands=["cancel"], state="*")
async def cmd_cancel(message: types.Message, state: FSMContext):
	await state.finish()
	await show_menu_screen(message.chat.id, "❌ Действие отменено.", reply_markup=get_main_menu_inline())


@dp.message_handler(state=CargoStates.waiting_for_recipient, content_types=[ContentType.TEXT])
async def handle_recipient_input(message: types.Message, state: FSMContext):
	code = await require_code_or_hint(message)
	if not code:
		await state.finish()
		return
	parsed = parse_recipient_input(message.text or "")
	if not parsed:
		await show_menu_screen(message.chat.id, "⚠️ Формат не распознан. Пришлите: ФИО; телефон; город. Или /cancel", reply_markup=get_main_menu_inline())
		return
	fio, phone, city = parsed
	await state.update_data(fio=fio, phone=phone, city=city)
	tracks = get_tracks(message.from_user.id)
	text = (
		"📤 Заявка на отправку груза\n\n"
		f"🆔 Код клиента: <code>{code}</code>\n"
		f"👤 Получатель: {fio}\n"
		f"📞 Телефон: {phone}\n"
		f"🏙️ Город доставки: {city}\n\n"
		"📚 Зарегистрированные треки:\n" + (format_tracks(tracks) if tracks else "Нет зарегистрированных трек-кодов") + "\n\n"
		"Выберите тип доставки:"
	)
	await CargoStates.choosing_delivery.set()
	await show_menu_screen(message.chat.id, text, reply_markup=delivery_keyboard(), parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data == "menu_clearhistory", state="*")
@dp.message_handler(lambda m: (m.text or "").strip() == "🧹 Очистить историю", state="*")
async def clear_history_entry(cb_or_msg, state: FSMContext):
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
		await show_menu_screen(tgt.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
		return

	tracks = get_tracks(user_id)
	shipments_total = count_user_shipments(user_id)
	if not tracks and shipments_total == 0:
		await show_menu_screen(tgt.chat.id, "ℹ️ История пуста. Очищать нечего.", reply_markup=get_main_menu_inline())
		return

	await show_menu_screen(tgt.chat.id, "Вы уверены, что хотите удалить всю историю (треки и грузы)? Это действие нельзя отменить.", reply_markup=clear_history_confirm_keyboard())


@dp.callback_query_handler(lambda c: c.data in ("clear_confirm", "clear_cancel"), state="*")
async def clear_history_confirm(callback: CallbackQuery, state: FSMContext):
	await bot.answer_callback_query(callback.id)
	if callback.data == "clear_cancel":
		await state.finish()
		await callback.message.edit_text("❌ Очистка отменена")
		await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
		return

	user_id = callback.from_user.id
	code = get_user_code(user_id)
	if not code:
		await state.finish()
		await callback.message.edit_text("Сначала получите личный код: нажмите «🔑 Получить код».")
		await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
		return

	deleted_tracks = delete_all_user_tracks(user_id)
	deleted_shipments = delete_all_user_shipments(user_id)
	await state.finish()
	await callback.message.edit_text(f"✅ История очищена. Удалено треков: {deleted_tracks}, грузов: {deleted_shipments}.")
	await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())


@dp.message_handler(state=TrackStates.waiting_for_track, content_types=[ContentType.TEXT])
async def handle_track_input(message: types.Message, state: FSMContext):
	code = await require_code_or_hint(message)
	if not code:
		await state.finish()
		return

	track = (message.text or "").strip().upper()
	if not is_valid_track_number(track):
		await message.answer("⚠️ Неверный формат трек-кода. Пришлите другой или /cancel")
		return

	# Сохраняем трек без выбора доставки. Доставку уточним при оформлении груза.
	try:
		add_track(message.from_user.id, track, "")
	except Exception as e:
		logger.exception("Failed to save track: %s", e)
		await message.answer("❌ Ошибка сохранения трека. Попробуйте позже.")
		return
	await state.finish()
	await message.answer(
		f"✅ Трек-код зарегистрирован: <code>{track}</code>\n\n"
		"Когда будете готовы отправить груз, нажмите «📤 Отправить груз». Все ваши треки будут переданы складу одним сообщением.",
		parse_mode="HTML",
	)
	await show_menu_screen(message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data.startswith("delivery_"), state=TrackStates.choosing_delivery)
async def choose_delivery(callback: CallbackQuery, state: FSMContext):
	await bot.answer_callback_query(callback.id)
	if callback.data == "delivery_cancel":
		await state.finish()
		await callback.message.edit_text("❌ Добавление трека отменено")
		await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
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
		await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
		return

	user_id = callback.from_user.id
	code = get_user_code(user_id)
	if not code:
		await state.finish()
		await callback.message.edit_text("Сначала получите личный код: нажмите «🔑 Получить код».")
		await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
		return

	data = await state.get_data()
	track = data["track"]
	# Регистрируем трек без выбора способа доставки; отправка на склад будет при оформлении груза
	try:
		add_track(user_id, track, "")
	except Exception as e:
		logger.exception("Failed to save track: %s", e)
		await state.finish()
		await callback.message.edit_text("❌ Ошибка сохранения трека. Попробуйте позже.")
		await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
		return

	await state.finish()
	await callback.message.edit_text(
		"✅ Трек-код зарегистрирован. Он будет передан сотруднику склада в составе вашей заявки на отправку груза.",
		parse_mode="HTML",
	)
	await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())


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
		await show_menu_screen(tgt.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
		return

	user_tracks = get_tracks(user_id)
	text_parts = []
	if user_tracks:
		text_parts.append("📦 Ваши треки:\n\n" + format_tracks(user_tracks))
	text_parts.append("📷 Отправьте трек-код, чтобы получить фото. Для отмены — /cancel")
	await show_menu_screen(tgt.chat.id, "\n\n".join(text_parts), reply_markup=(clear_history_entry_keyboard() if user_tracks else None), parse_mode=("HTML" if user_tracks else None))
	await PhotoStates.waiting_for_track.set()


@dp.message_handler(lambda m: (m.text or "").strip() == "📷 Фотоконтроль", state="*")
async def menu_photokontrol_reply_button(message: types.Message, state: FSMContext):
	await menu_photokontrol(message, state)


@dp.message_handler(state=PhotoStates.waiting_for_track, content_types=[ContentType.TEXT])
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
		await show_menu_screen(message.chat.id, f"📭 Фото по треку <code>{track}</code> пока не загружены.", reply_markup=get_main_menu_inline(), parse_mode="HTML")
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
	await show_menu_screen(message.chat.id, "✅ Все доступные фото отправлены.", reply_markup=get_main_menu_inline())
	# Предложим возможность очистить историю
	user_tracks = get_tracks(message.from_user.id)
	if user_tracks:
		await show_menu_screen(message.chat.id, "Нужно очистить историю треков?", reply_markup=clear_history_entry_keyboard())


@dp.callback_query_handler(lambda c: c.data in ("cargo_confirm", "cargo_edit", "cargo_cancel"), state=CargoStates.confirming)
async def confirm_cargo(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    if callback.data == "cargo_cancel":
        await state.finish()
        await callback.message.edit_text("❌ Отправка груза отменена")
        await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
        return
    if callback.data == "cargo_edit":
        await CargoStates.waiting_for_recipient.set()
        await show_menu_screen(callback.message.chat.id, "✍️ Пришлите данные получателя одной строкой: ФИО; телефон; город доставки\nДля отмены — /cancel", reply_markup=get_main_menu_inline())
        return

    user_id = callback.from_user.id
    code = get_user_code(user_id)
    if not code:
        await state.finish()
        await callback.message.edit_text("Сначала получите личный код: нажмите «🔑 Получить код».")
        await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
        return

    data = await state.get_data()
    fio, phone, city = data.get("fio", ""), data.get("phone", ""), data.get("city", "")
    delivery_key = data.get("delivery")
    delivery_name = DELIVERY_TYPES.get(delivery_key, {}).get("name", "Не указано") if delivery_key else "Не указано"
    set_recipient(user_id, fio, phone, city)

    tracks = get_tracks(user_id)
    cargo_num = get_next_cargo_num(user_id)
    cargo_code = f"{code}-{cargo_num}"
    try:
        # Статус по умолчанию: на сборке
        create_shipment(user_id, cargo_num, cargo_code, fio, phone, city, status="на сборке")
    except Exception as e:
        logger.exception("Failed to create shipment: %s", e)
        await state.finish()
        await callback.message.edit_text("❌ Ошибка создания отправки. Попробуйте позже.")
        await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
        return

    full_name = callback.from_user.full_name or ""
    username = f"@{callback.from_user.username}" if callback.from_user.username else "не указан"
    # Список треков без дубликатов
    seen = set()
    unique_track_lines = []
    for idx, (t, _d) in enumerate([(t, d) for (t, d) in tracks], start=1):
        if t in seen:
            continue
        seen.add(t)
        unique_track_lines.append(f"{len(seen)}. <code>{t}</code>")

    text = (
        "📦 <b>ЗАЯВКА НА ОТПРАВКУ ГРУЗА</b>\n\n"
        f"🆔 Код клиента: <code>{code}</code>\n"
        f"📦 Номер груза: <b>{cargo_code}</b>\n\n"
        f"👤 Клиент: {full_name}\n"
        f"📱 Username: {username}\n"
        f"🆔 Telegram ID: <code>{user_id}</code>\n\n"
        f"👤 Получатель: {fio}\n"
        f"📞 Телефон: {phone}\n"
        f"🏙️ Город доставки: {city}\n"
        f"🚚 Способ доставки: {delivery_name}\n\n"
        "📚 Треки клиента:\n" + ("\n".join(unique_track_lines) if unique_track_lines else "Нет зарегистрированных трек-кодов")
    )
    if WAREHOUSE_ID:
        try:
            await bot.send_message(WAREHOUSE_ID, text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Failed to notify warehouse about cargo: %s", e)

    await state.finish()
    await callback.message.edit_text(
        "✅ Заявка отправлена сотруднику склада. Ожидайте подтверждения.\n"
        f"Ваш номер груза: <b>{cargo_code}</b>",
        parse_mode="HTML",
    )
    await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())

@dp.callback_query_handler(lambda c: c.data.startswith("delivery_"), state=CargoStates.choosing_delivery)
async def choose_cargo_delivery(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    if callback.data == "delivery_cancel":
        await state.finish()
        await callback.message.edit_text("❌ Оформление отправки отменено")
        await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
        return

    delivery_key = callback.data.replace("delivery_", "")
    delivery_name = DELIVERY_TYPES.get(delivery_key, {}).get("name", "Не указано")
    await state.update_data(delivery=delivery_key)

    data = await state.get_data()
    user_id = callback.from_user.id
    code = get_user_code(user_id) or "—"
    fio, phone, city = data.get("fio", ""), data.get("phone", ""), data.get("city", "")
    tracks = get_tracks(user_id)

    # Список треков без дубликатов
    seen = set()
    unique_track_lines = []
    for (t, _d) in tracks:
        if t in seen:
            continue
        seen.add(t)
        unique_track_lines.append(f"{len(seen)}. <code>{t}</code>")

    text = (
        "📤 Заявка на отправку груза\n\n"
        f"🆔 Код клиента: <code>{code}</code>\n"
        f"👤 Получатель: {fio}\n"
        f"📞 Телефон: {phone}\n"
        f"🏙️ Город доставки: {city}\n"
        f"🚚 Способ доставки: {delivery_name}\n\n"
        "📚 Зарегистрированные треки:\n" + ("\n".join(unique_track_lines) if unique_track_lines else "Нет зарегистрированных трек-кодов") + "\n\n"
        "Подтвердить отправку?"
    )
    await CargoStates.confirming.set()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=cargo_confirm_keyboard())


@dp.callback_query_handler(lambda c: c.data == "menu_warehouse", state="*")
async def menu_warehouse(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    await state.finish()
    await show_menu_screen(callback.message.chat.id, "🏭 Раздел склада:", reply_markup=warehouse_menu_keyboard())


@dp.callback_query_handler(lambda c: c.data == "back_main", state="*")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    await state.finish()
    await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())


@dp.callback_query_handler(lambda c: c.data == "menu_status", state="*")
async def menu_status(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    await state.finish()
    await show_menu_screen(callback.message.chat.id, "📦 Статус груза:", reply_markup=cargo_status_menu_keyboard())


def _format_cargo_list(title: str, items: list[str]) -> str:
    if not items:
        return f"{title}: пусто"
    lines = [f"{idx}. <code>{code}</code>" for idx, code in enumerate(items, start=1)]
    return f"{title} (всего: {len(items)}):\n" + "\n".join(lines)


@dp.callback_query_handler(lambda c: c.data in ("status_building", "status_shipped"), state="*")
async def menu_status_list(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback.id)
    await state.finish()
    user_id = callback.from_user.id
    code = get_user_code(user_id)
    if not code:
        await show_menu_screen(callback.message.chat.id, "Сначала получите личный код: нажмите «🔑 Получить код».", reply_markup=get_main_menu_inline())
        return
    status_value = "на сборке" if callback.data == "status_building" else "отгружен"
    try:
        cargo_codes = list_user_shipments_by_status(user_id, status_value)
    except Exception:
        cargo_codes = []
    title = "🧰 На сборке" if callback.data == "status_building" else "✅ Отгруженные"
    text = _format_cargo_list(title, cargo_codes)
    await show_menu_screen(callback.message.chat.id, text, reply_markup=cargo_status_menu_keyboard(), parse_mode="HTML")
    # Также предложим вернуться в главное меню
    await show_menu_screen(callback.message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())
@dp.message_handler(lambda m: (getattr(m, "caption", "") or "").strip().lower().startswith("/shipped"), content_types=[ContentType.PHOTO], state="*")
async def admin_shipped_with_photo(message: types.Message, state: FSMContext):
	# Если администратор отправляет фото с подписью вида "/shipped EM.." в одном сообщении
	if message.from_user.id not in {MANAGER_ID, WAREHOUSE_ID}:
		return
	caption_text = (message.caption or "").strip()

	cargo_code = extract_cargo_code(caption_text)
	if not cargo_code:
		await message.answer("Укажите номер груза в подписи, например: /shipped EM03-00001-1")
		return
	user_id = get_user_id_by_cargo_code(cargo_code)
	if not user_id:
		await message.answer(f"Груз с номером <code>{cargo_code}</code> не найден.", parse_mode="HTML")
		return
	# Обновляем статус: отгружен
	try:
		update_shipment_status(cargo_code, "отгружен")
	except Exception:
		pass
	try:
		await bot.send_photo(
			user_id,
			message.photo[-1].file_id,
			caption=f"📦 Ваш груз <b>{cargo_code}</b> упакован и отгружен в транспортную компанию.",
			parse_mode="HTML",
		)
		await message.answer("✅ Уведомление клиенту отправлено")
	except Exception as e:
		logger.exception("Failed to notify user about shipped cargo (single message): %s", e)
		await message.answer("❌ Ошибка отправки уведомления клиенту")
@dp.message_handler(content_types=[ContentType.PHOTO], state="*")
async def warehouse_photo_upload(message: types.Message, state: FSMContext):
	# Обрабатываем фото только от администраторов (склад или менеджер)
	if message.from_user.id not in {MANAGER_ID, WAREHOUSE_ID}:
		return

	# Если это фото с подписью вида "/shipped ...", отдаем обработку специализированному хендлеру
	if (message.caption or "").strip().lower().startswith("/shipped"):
		return

	# Если сейчас идет сессия отправки груза (/shipped),
	# не пытаемся распознавать трек из подписи и не отвечаем ошибкой
	# — фото будут обработаны специализированным хендлером для /shipped
	current_state = await state.get_state()
	if current_state in {
		AdminShipmentStates.waiting_for_media.state,
		AdminShipmentStates.waiting_for_cargo_code.state,
	}:
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


@dp.message_handler(commands=["shipped"], state="*")
async def admin_shipped_start(message: types.Message, state: FSMContext):
	# Только менеджер или склад
	if message.from_user.id not in {MANAGER_ID, WAREHOUSE_ID}:
		return
	await state.finish()
	args = (message.get_args() or "").strip()
	cargo_code = extract_cargo_code(args)
	if not cargo_code:
		await message.answer("Укажите номер груза, например: /shipped EM03-00001-1")
		return
	user_id = get_user_id_by_cargo_code(cargo_code)
	if not user_id:
		await message.answer(f"Груз с номером <code>{cargo_code}</code> не найден.", parse_mode="HTML")
		return
	await state.update_data(cargo_code=cargo_code, target_user_id=user_id)
	await AdminShipmentStates.waiting_for_media.set()
	await message.answer(
		"Отправьте одно или несколько фото груза/накладной одним или несколькими сообщениями. Когда закончите — отправьте текст 'готово' или команду /done. Для отмены — /cancel."
	)


@dp.message_handler(lambda m: m.text and m.text.lower() in {"готово", "done", "/done"}, state=AdminShipmentStates.waiting_for_media)
async def admin_shipped_finish(message: types.Message, state: FSMContext):
	data = await state.get_data()
	user_id = data.get("target_user_id")
	cargo_code = data.get("cargo_code")
	if not user_id or not cargo_code:
		await state.finish()
		await message.answer("Сессия сброшена. Повторите /shipped.")
		return
	buffer_key = f"{message.from_user.id}:{cargo_code}"
	media_items = _admin_album_buffers.get(buffer_key, [])
	if not media_items:
		await state.finish()
		await message.answer("Нет прикрепленных фото. Отправьте хотя бы одно фото перед завершением.")
		return

	# Сформируем медиа группу (первые 10 по ограничению Telegram)
	group: list[InputMediaPhoto] = []
	for idx, item in enumerate(media_items[:10]):
		caption = (f"📦 Отправка груза <b>{cargo_code}</b>" if idx == 0 else None)
		group.append(InputMediaPhoto(media=item["file_id"], caption=caption, parse_mode="HTML"))

	try:
		if len(group) == 1:
			await bot.send_photo(user_id, group[0].media, caption=group[0].caption, parse_mode="HTML")
		else:
			await bot.send_media_group(user_id, group)
		await bot.send_message(user_id, f"✅ Ваш груз <b>{cargo_code}</b> отправлен. Фото во вложении.", parse_mode="HTML")
		await message.answer("✅ Уведомление клиенту отправлено")
	except Exception as e:
		logger.exception("Failed to notify user about shipped cargo: %s", e)
		await message.answer("❌ Ошибка отправки уведомления клиенту")

	# Обновляем статус отправки: отгружен
	try:
		update_shipment_status(cargo_code, "отгружен")
	except Exception:
		pass

	# Очистим буфер и состояние
	_admin_album_buffers.pop(buffer_key, None)
	await state.finish()


@dp.message_handler(content_types=[ContentType.PHOTO], state=AdminShipmentStates.waiting_for_media)
async def admin_shipped_collect_media(message: types.Message, state: FSMContext):
	data = await state.get_data()
	cargo_code = data.get("cargo_code")
	if not cargo_code:
		return
	buffer_key = f"{message.from_user.id}:{cargo_code}"
	items = _admin_album_buffers.setdefault(buffer_key, [])
	items.append({"file_id": message.photo[-1].file_id})
	await message.answer("Фото добавлено. Отправьте еще или напишите 'готово'.")

@dp.message_handler(commands=["findtracks"], state="*")
async def admin_findtracks(message: types.Message, state: FSMContext):
	await state.finish()
	# Only manager or warehouse can use
	if message.from_user.id not in {MANAGER_ID, WAREHOUSE_ID}:
		return
	args = (message.get_args() or "").strip()
	if not args:
		await message.answer("Использование: /findtracks EM03-00001")
		return
	code = args.upper()
	user_id = get_user_id_by_code(code)
	if not user_id:
		await message.answer(f"Пользователь с кодом <code>{code}</code> не найден.", parse_mode="HTML")
		return
	# Получаем данные пользователя из Telegram
	full_name = "—"
	username = "не указан"
	try:
		chat = await bot.get_chat(user_id)
		first_name = getattr(chat, "first_name", None) or ""
		last_name = getattr(chat, "last_name", None) or ""
		full_name = (f"{first_name} {last_name}").strip() or "—"
		if getattr(chat, "username", None):
			username = f"@{chat.username}"
	except Exception:
		pass

	tracks = get_tracks(user_id)
	user_block = (
		"🧑‍💼 Данные клиента\n\n"
		f"🆔 Код клиента: <code>{code}</code>\n"
		f"👤 Имя: {full_name}\n"
		f"📱 Username: {username}\n"
		f"🆔 Telegram ID: <code>{user_id}</code>\n"
	)
	if not tracks:
		await message.answer(
			user_block + "\nУ пользователя нет зарегистрированных треков.",
			parse_mode="HTML",
		)
		return
	text = (
		user_block
		+ "\n📦 Треки:\n\n"
		+ format_tracks(tracks)
	)
	await message.answer(text, parse_mode="HTML")


@dp.message_handler()
async def fallback(message: types.Message):
	await show_menu_screen(message.chat.id, "Выберите действие:", reply_markup=get_main_menu_inline())


async def on_startup(dp: Dispatcher):
	init_db()
	try:
		dp.middleware.setup(ActivityMiddleware())
	except Exception:
		pass

	# Background reminder loop
	async def reminder_loop():
		while True:
			try:
				# 5-day: address
				for uid in get_users_for_address_reminder(days=5):
					try:
						await bot.send_message(int(uid), "Возникли сложности ? Свяжись с менеджером, мы все подскажем!")
						mark_address_reminder_sent(int(uid))
					except Exception:
						pass
				# 15-day: send cargo
				for uid in get_users_for_sendcargo_reminder(days=15):
					try:
						await bot.send_message(int(uid), "Вы уже сделали свои покупки ? Мы готовы их Вам отправить!")
						mark_sendcargo_reminder_sent(int(uid))
					except Exception:
						pass
				# 30-day: inactivity
				for uid in get_users_for_inactive_reminder(days=30):
					try:
						await bot.send_message(int(uid), "Совершайте свои покупки из Китая вместе с ProBuy!")
						mark_inactive_reminder_sent(int(uid))
					except Exception:
						pass
			except Exception:
				pass
			await asyncio.sleep(3600)

	asyncio.get_running_loop().create_task(reminder_loop())
	try:
		await bot.delete_webhook(drop_pending_updates=True)
	except Exception:
		pass
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
	executor.start_polling(dp, skip_updates=False, on_startup=on_startup, on_shutdown=on_shutdown)
