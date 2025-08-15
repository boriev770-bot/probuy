import re
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Command
import os

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192
USERS_FILE = "users.txt"  # Файл для хранения ID пользователей

# Списки для хранения данных
waiting_for_order = set()
active_users = set()  # Для хранения активных пользователей в памяти

# Список частых вопросов и ответов
FAQ = {
    r"(?i)\b(сделать|заказ|заказать|оформить)\b": 
        "Для заказа напишите слово 'оператор' и опишите то, что хотели бы заказать. Менеджер с Вами свяжется.💬",
    r"(?i)\b(сколько|стоимость|цена|стоит|доставка)\b": 
        "Стоимость доставки рассчитывается индивидуально исходя из плотности и веса груза. Напишите боту слово 'оператор', и менеджер с вами свяжется.",
    r"(?i)\b(время|срок|когда|дней|сроки|доставят)\b": 
        "Сроки доставки быстрым авто: 10-15 дней, медленным авто: 15-20 дней. (Сроки доставки указаны до рынка Южные Ворота в г.Москва.)"
}

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Функции для работы с пользователями
def save_user(user_id):
    """Сохраняет ID пользователя в файл"""
    user_id = str(user_id)
    if user_id not in active_users:
        active_users.add(user_id)
        with open(USERS_FILE, 'a') as f:
            f.write(f"{user_id}\n")

def load_users():
    """Загружает список пользователей из файла"""
    if not os.path.exists(USERS_FILE):
        return set()
    
    with open(USERS_FILE, 'r') as f:
        return {line.strip() for line in f if line.strip()}

def find_best_match(user_text):
    """Поиск ответа в FAQ по ключевым словам"""
    user_text = user_text.lower()
    for pattern, answer in FAQ.items():
        if re.search(pattern, user_text):
            return answer
    return None

# Обработчики команд
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    save_user(message.from_user.id)
    await message.answer(
        "Привет! 🤝🏻 Мы компания, занимающаяся поиском, выкупом и доставкой товаров из Китая.\n\n"
        "Напиши свой вопрос, а я постараюсь найти на него ответ.\n"
        "Например:\n"
        "- Сколько стоит доставка? 🚚\n"
        "- Как сделать заказ? 📥\n\n"
        "Если нужен живой человек — напиши слово 'оператор'.\n"
        "Чтобы оформить заказ — выберите /buy в меню."
    )

@dp.message_handler(commands=['buy'])
async def ask_order(message: types.Message):
    user_id = message.from_user.id
    waiting_for_order.add(user_id)
    await message.answer("Расскажите, что вы хотите заказать? В каком количестве? 📦\nМожете прикрепить фото или описание товара.")

@dp.message_handler(Command('broadcast'), user_id=ADMIN_ID)
async def broadcast_message(message: types.Message):
    """Рассылка сообщений всем пользователям (только для админа)"""
    if not message.reply_to_message:
        await message.answer("ℹ️ Используйте команду /broadcast в ответ на сообщение, которое хотите разослать")
        return
    
    users = load_users()
    if not users:
        await message.answer("❌ Нет пользователей для рассылки")
        return
    
    await message.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей...")
    
    success = 0
    failed = 0
    
    for user_id in users:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.reply_to_message.message_id
            )
            success += 1
            await asyncio.sleep(0.1)  # Задержка для избежания ограничений
        except Exception as e:
            failed += 1
    
    await message.answer(
        f"✅ Рассылка завершена:\n"
        f"Успешно: {success}\n"
        f"Не удалось: {failed}"
    )

# Основной обработчик сообщений
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_all_messages(message: types.Message):
    user_id = str(message.from_user.id)
    save_user(user_id)  # Сохраняем пользователя при любом сообщении
    
    text = message.text.lower() if message.text else ""

    # Обработка заказов
    if int(user_id) in waiting_for_order:
        caption = (
            f"📦 Новый заказ!\n"
            f"👤 Имя: {message.from_user.full_name}\n"
            f"🔗 Username: @{message.from_user.username or 'нет'}"
        )

        if message.text:
            caption += f"\n✉️ Сообщение: {message.text}"
            await bot.send_message(ADMIN_ID, caption)
        elif message.photo:
            await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption)
        elif message.document:
            await bot.send_document(ADMIN_ID, message.document.file_id, caption=caption)
        else:
            await bot.send_message(ADMIN_ID, caption + "\n[⚠️ Пользователь отправил нераспознанный тип сообщения]")

        await message.answer("✅ Спасибо! Мы получили ваш заказ. Менеджер скоро свяжется с вами.💬")
        waiting_for_order.remove(int(user_id))
        return

    # Обработка запроса оператора
    if "оператор" in text:
        await message.answer("🔄 Оператор скоро свяжется с Вами. Спасибо за обращение!🫂")
        await bot.send_message(
            ADMIN_ID,
            f"📩 Запрос к оператору!\n"
            f"👤 Имя: {message.from_user.full_name}\n"
            f"🔗 Username: @{message.from_user.username or 'нет'}\n"
            f"✉️ Сообщение: {message.text if message.text else '📎 Пользователь отправил медиа-файл'}"
        )
        return

    # Поиск ответа в FAQ (только для текстовых сообщений)
    if message.text:
        response = find_best_match(text)
        if response:
            await message.answer(response)
            return

    # Ответ по умолчанию
    await message.answer("❓ Извините, я не нашёл ответа на этот вопрос. Напишите слово 'оператор' для связи с менеджером.")

# Загрузка пользователей при старте
active_users.update(load_users())

async def main():
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())
