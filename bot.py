import re
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os

# --- НАСТРОЙКИ ---
TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192
USERS_FILE = "users.txt"

# Хранилища данных
waiting_for_order = set()
active_users = set()
user_data = {}
waiting_for_broadcast = False

FAQ = {
    r"(?i)\b(сделать|заказ|заказать|оформить)\b": 
        "Для заказа напишите слово 'оператор' и опишите товар. Менеджер свяжется с Вами 💬",
    r"(?i)\b(сколько|стоимость|цена|стоит|доставка)\b": 
        "Стоимость доставки рассчитывается индивидуально. Напишите 'оператор' для точного расчета.",
    r"(?i)\b(время|срок|когда|дней|сроки|доставят)\b": 
        "Сроки доставки: 10-20 дней в зависимости от способа (до Москвы)."
}

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# --- Работа с пользователями ---
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
                user_id, username, first_name = line.strip().split(',')[:3]
                active_users.add(user_id)
                user_data[user_id] = {
                    'username': username if username else None,
                    'first_name': first_name if first_name else None
                }

# --- Поиск в FAQ ---
def find_best_match(text):
    if not text:
        return None
    text = text.lower()
    for pattern, answer in FAQ.items():
        if re.search(pattern, text):
            return answer
    return None

# --- Уведомление админа ---
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
    elif message.video:
        await bot.send_video(ADMIN_ID, message.video.file_id, caption=caption, reply_markup=markup)
    else:
        await bot.send_message(ADMIN_ID, caption, reply_markup=markup)

# --- Команды ---
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    await message.answer(
        "🤖 Бот для заказов из Китая\n\n"
        "Команды:\n"
        "/buy — оформить заказ\n"
        "'оператор' — связаться с менеджером"
    )

@dp.message_handler(commands=['buy'])
async def ask_order(message: types.Message):
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    waiting_for_order.add(user.id)
    await message.answer(
        "📝 Опишите заказ:\n"
        "1. Название товара\n"
        "2. Количество\n"
        "3. Телефон\n\n"
        "Можно прикрепить фото или документ"
    )

# --- Рассылка ---
@dp.message_handler(commands=['broadcast'])
async def broadcast_start(message: types.Message):
    global waiting_for_broadcast
    if message.from_user.id != ADMIN_ID:
        return
    waiting_for_broadcast = True
    await message.answer("📢 Отправьте сообщение (текст/фото/видео/документ) для рассылки.")

# --- Обработка любых сообщений ---
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_message(message: types.Message):
    global waiting_for_broadcast
    user = message.from_user
    save_user(user.id, user.username, user.first_name)

    # --- РАССЫЛКА ---
    if waiting_for_broadcast and message.from_user.id == ADMIN_ID:
        waiting_for_broadcast = False
        users_list = list(active_users)
        total = len(users_list)
        count = 0
        await message.answer(f"📤 Начинаю рассылку ({total} пользователей)")

        for i in range(0, total, 30):
            batch = users_list[i:i+30]
            for user_id in batch:
                try:
                    if message.text:
                        await bot.send_message(user_id, message.text)
                    elif message.photo:
                        await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or "")
                    elif message.video:
                        await bot.send_video(user_id, message.video.file_id, caption=message.caption or "")
                    elif message.document:
                        await bot.send_document(user_id, message.document.file_id, caption=message.caption or "")
                    count += 1
                except:
                    continue
            await asyncio.sleep(2)

        await message.answer(f"✅ Разослано: {count}/{total}")
        return

    # --- ОФОРМЛЕНИЕ ЗАКАЗА ---
    if user.id in waiting_for_order:
        await notify_admin(message, "заказ")
        waiting_for_order.remove(user.id)
        await message.answer("✅ Заказ принят! Менеджер скоро свяжется.")
        return

    # --- ЗАПРОС ОПЕРАТОРА ---
    if message.text and "оператор" in message.text.lower():
        await notify_admin(message, "запрос оператора")
        await message.answer("🔄 Менеджер скоро с вами свяжется.")
        return

    # --- FAQ ---
    if message.text:
        answer = find_best_match(message.text)
        if answer:
            await message.answer(answer)
        else:
            await message.answer("❓ Не нашел ответа. Напишите 'оператор' для связи.")

# --- Запуск ---
load_users()

async def main():
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())