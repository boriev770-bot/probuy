import re
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192
USERS_FILE = "users.txt"

# Хранилища данных
waiting_for_order = set()
active_users = set()
user_data = {}  # Для хранения дополнительной информации о пользователях

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

def save_user(user_id, username=None, first_name=None):
    """Сохраняет данные пользователя"""
    user_id = str(user_id)
    if user_id not in active_users:
        active_users.add(user_id)
        user_data[user_id] = {
            'username': username,
            'first_name': first_name,
            'last_activity': asyncio.get_event_loop().time()
        }
        with open(USERS_FILE, 'a') as f:
            f.write(f"{user_id},{username or ''},{first_name or ''}\n")

def load_users():
    """Загружает пользователей из файла"""
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
    """Поиск ответа в FAQ"""
    if not text:
        return None
    text = text.lower()
    for pattern, answer in FAQ.items():
        if re.search(pattern, text):
            return answer
    return None

async def notify_admin(message: types.Message, message_type="запрос"):
    """Отправляет уведомление админу с кнопкой ответа"""
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
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, 
                           caption=caption, reply_markup=markup)
    elif message.document:
        await bot.send_document(ADMIN_ID, message.document.file_id, 
                              caption=caption, reply_markup=markup)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    await message.answer(
        "🤖 Бот для заказов из Китая\n\n"
        "Доступные команды:\n"
        "Заказать - оформить заказ\n"
        "'оператор' - связаться с менеджером\n\n"
        "Задайте вопрос о доставке или заказе!"
    )

@dp.message_handler(commands=['buy'])
async def ask_order(message: types.Message):
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    waiting_for_order.add(user.id)
    await message.answer(
        "📝 Оформление заказа\n\n"
        "Опишите:\n"
        "1. Название товара\n"
        "2. Количество\n"
        "3. Номер телефона\n\n"
        "Можно прикрепить фото или документ"
    )

@dp.message_handler(Command('broadcast'), user_id=ADMIN_ID)
async def broadcast(message: types.Message):
    if not message.reply_to_message:
        await message.answer("ℹ️ Ответьте /broadcast на сообщение для рассылки")
        return
    
    users = [uid for uid in active_users if uid in user_data]
    if not users:
        await message.answer("❌ Нет пользователей для рассылки")
        return
    
    await message.answer(f"⏳ Рассылка для {len(users)} пользователей...")
    
    success = 0
    for user_id in users:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.reply_to_message.message_id
            )
            success += 1
            await asyncio.sleep(0.1)
        except:
            continue
    
    await message.answer(f"✅ Отправлено: {success}/{len(users)}")

@dp.callback_query_handler(lambda c: c.data.startswith('reply_'))
async def process_reply(callback: types.CallbackQuery):
    user_id = callback.data.split('_')[1]
    await callback.message.answer(
        f"✏️ Ответ для пользователя ID: {user_id}\n"
        f"Введите текст ответа:"
    )
    # Здесь можно сохранить user_id для следующего сообщения

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_text(message: types.Message):
    user = message.from_user
    save_user(user.id, user.username, user.first_name)
    text = message.text.lower()

    if user.id in waiting_for_order:
        await notify_admin(message, "заказ")
        waiting_for_order.remove(user.id)
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
            "❓ Я не нашел ответа на ваш вопрос\n"
            "Попробуйте спросить о:\n"
            "- Стоимости доставки\n"
            "- Сроках доставки\n"
            "- Как сделать заказ\n\n"
            "Или напишите 'оператор' для связи"
        )

@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_media(message: types.Message):
    user = message.from_user
    save_user(user.id, user.username, user.first_name)

    if user.id in waiting_for_order:
        await notify_admin(message, "заказ с медиа")
        await message.answer("📎 Файл получен. Добавьте текстовое описание если нужно.")
    else:
        await message.answer("📤 Пожалуйста, отправьте текстовое сообщение")

# Инициализация
load_users()

async def main():
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
