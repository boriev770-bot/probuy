import re
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import os

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192
USERS_FILE = "users.txt"

# Хранилища данных
waiting_for_order = set()
active_users = set()
user_data = {}

FAQ = {
    r"(?i)\b(сделать|заказ|заказать|оформить)\b": 
        "Для заказа напишите слово 'оператор' или команду /manager и опишите товар. Менеджер свяжется с Вами 💬",
    r"(?i)\b(сколько|стоимость|цена|стоит|доставка)\b": 
        "Стоимость доставки рассчитывается индивидуально. Напишите 'оператор' или /manager для точного расчета.",
    r"(?i)\b(время|срок|когда|дней|сроки|доставят)\b": 
        "Сроки доставки: 10-20 дней в зависимости от способа (до Москвы)."
}

# FSM для ответа админу
class ReplyState(StatesGroup):
    waiting_for_reply = State()

# FSM для рассылки
class BroadcastState(StatesGroup):
    waiting_for_message = State()

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

def save_user(user_id, username=None, first_name=None):
    user_id = str(user_id)
    if user_id not in active_users:
        active_users.add(user_id)
        user_data[user_id] = {
            'username': username,
            'first_name': first_name
        }
        with open(USERS_FILE, 'a') as f:
            f.write(f"{user_id},{username or ''},{first_name or ''}\n")

def load_users():
    if not os.path.exists(USERS_FILE):
        return
    with open(USERS_FILE, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    user_id, username, first_name = parts[0], parts[1], parts[2]
                    active_users.add(user_id)
                    user_data[user_id] = {
                        'username': username if username else None,
                        'first_name': first_name if first_name else None
                    }

def find_best_match(text):
    if not text:
        return None
    text = text.lower()
    for pattern, answer in FAQ.items():
        if re.search(pattern, text):
            return answer
    return None

async def notify_admin(message: types.Message, message_type="запрос"):
    user = message.from_user
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        "✉️ Ответить", 
        callback_data=f"reply_{user.id}"
    ))
    caption = (
        f"📢 Новый {message_type}!\n"
        f"🆔 ID: {user.id}\n"
        f"👤 Имя: {user.full_name}\n"
        f"🔗 Username: @{user.username if user.username else 'нет'}\n"
    )
    if message.text:
        caption += f"✉️ Сообщение: {message.text}"
        await bot.send_message(ADMIN_ID, caption, reply_markup=markup)
    elif message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, reply_markup=markup)
    elif message.document:
        await bot.send_document(ADMIN_ID, message.document.file_id, caption=caption, reply_markup=markup)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    await message.answer(
        "🤖 Бот для заказов из Китая\n\n"
        "Доступные команды:\n"
        "/buy — оформить заказ\n"
        "/manager или 'оператор' — связаться с менеджером\n"
        "/broadcast — сделать рассылку (только для администратора)\n\n"
        "Задайте вопрос о доставке или заказе!"
    )

@dp.message_handler(commands=['buy'])
async def ask_order(message: types.Message):
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    waiting_for_order.add(message.from_user.id)
    await message.answer(
        "📝 Оформление заказа\n\n"
        "Опишите:\n"
        "1. Название товара\n"
        "2. Количество\n"
        "3. Номер телефона\n\n"
        "Можно прикрепить фото или документ"
    )

@dp.message_handler(commands=['manager'])
async def call_manager(message: types.Message):
    await notify_admin(message, "запрос оператора")
    await message.answer("🔄 Вас скоро свяжут с менеджером!")

# Ответ админу
@dp.callback_query_handler(lambda c: c.data.startswith('reply_'))
async def process_reply(callback: types.CallbackQuery, state: FSMContext):
    target_user_id = callback.data.split('_')[1]
    await state.update_data(target_user_id=target_user_id)
    await callback.message.answer("✏️ Введите сообщение для отправки пользователю:")
    await ReplyState.waiting_for_reply.set()

@dp.message_handler(state=ReplyState.waiting_for_reply, content_types=types.ContentTypes.ANY)
async def send_admin_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_user_id = int(data['target_user_id'])
    try:
        if message.text:
            await bot.send_message(target_user_id, f"💬 Сообщение от менеджера:\n{message.text}")
        elif message.photo:
            await bot.send_photo(target_user_id, message.photo[-1].file_id, caption="💬 Сообщение от менеджера")
        elif message.document:
            await bot.send_document(target_user_id, message.document.file_id, caption="💬 Сообщение от менеджера")
        await message.answer("✅ Сообщение отправлено пользователю.")
    except:
        await message.answer("❌ Не удалось отправить сообщение пользователю.")
    await state.finish()

# Рассылка
@dp.message_handler(commands=['broadcast'])
async def broadcast_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда доступна только администратору.")
        return
    await message.answer("✏️ Отправьте текст, фото или документ для рассылки:")
    await BroadcastState.waiting_for_message.set()

@dp.message_handler(state=BroadcastState.waiting_for_message, content_types=types.ContentTypes.ANY)
async def broadcast_send(message: types.Message, state: FSMContext):
    sent_count = 0
    failed_count = 0
    for user_id in list(active_users):
        try:
            if message.text:
                await bot.send_message(user_id, message.text)
            elif message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or "")
            elif message.document:
                await bot.send_document(user_id, message.document.file_id, caption=message.caption or "")
            sent_count += 1
        except:
            failed_count += 1
    await message.answer(f"📢 Рассылка завершена!\n✅ Успешно: {sent_count}\n❌ Ошибок: {failed_count}")
    await state.finish()

# Обработка текстовых сообщений
@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = message.text.lower()

    if message.from_user.id in waiting_for_order:
        await notify_admin(message, "заказ")
        waiting_for_order.remove(message.from_user.id)
        await message.answer("✅ Заказ принят! Ожидайте сообщения от менеджера.")
        return

    if "оператор" in text:
        await notify_admin(message, "запрос оператора")
        await message.answer("🔄 Вас скоро свяжут с менеджером!")
        return

    answer = find_best_match(text)
    if answer:
        await message.answer(answer)
    else:
        await message.answer(
            "❓ Я не нашел ответа на ваш вопрос.\n"
            "Напишите 'оператор' или /manager для связи с менеджером."
        )

# Обработка медиа
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_media(message: types.Message):
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    if message.from_user.id in waiting_for_order:
        await notify_admin(message, "заказ с медиа")
        await message.answer("📎 Файл получен. Добавьте текстовое описание если нужно.")
    else:
        await message.answer("📤 Пожалуйста, отправьте текстовое сообщение")

# Запуск
load_users()
async def main():
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())