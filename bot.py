import re
import asyncio
from aiogram import Bot, Dispatcher, types

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192  # Ваш Telegram ID

# Список пользователей, ожидающих обработки заказа
waiting_for_order = set()

# Список частых вопросов и ответов
FAQ = {
    r"(сдела.*|заказ.*)": "Для заказа напишите слово 'оператор' и опишите то, что хотели бы заказать. Менеджер с Вами свяжется.💬",
    r"(сколь.*|стои.*|доставк.*|цена.*)": "Стоимость доставки рассчитывается индивидуально исходя из плотности и веса груза. Напишите боту слово 'оператор', и менеджер с вами свяжется.",
    r"(время.*|срок.*|когда.*придет.*|через.*дней.*|сроки.*)": "Сроки доставки быстрым авто: 10-15 дней, медленным авто: 15-20 дней. (Сроки доставки указаны до рынка Южные Ворота в г.Москва.)"
}

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

def find_best_match(user_text):
    user_text = user_text.lower()
    for pattern, answer in FAQ.items():
        if re.search(pattern, user_text):
            return answer
    return None

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "Привет! 🤝🏻 Напиши свой вопрос, а я постараюсь найти на него ответ.\n"
        "Например: 'Сколько стоит доставка?'🚚 или 'Как сделать заказ?📥'\n"
        "Если нужен живой человек — напиши слово 'оператор'.\n"
        "Чтобы оформить заказ — выберите /buy в меню."
    )

@dp.message_handler(commands=['buy'])
async def ask_order(message: types.Message):
    user_id = message.from_user.id
    waiting_for_order.add(user_id)
    await message.answer("Расскажите, что вы хотите заказать? В каком количестве?📦")

@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_all_messages(message: types.Message):
    user_id = message.from_user.id
    text = message.text.lower() if message.text else ""

    # Обработка заказов
    if user_id in waiting_for_order:
        caption = (f"📦 Новый заказ!\n"
                  f"Имя: {message.from_user.full_name}\n"
                  f"Username: @{message.from_user.username or 'нет'}")

        if message.text:
            caption += f"\nСообщение: {message.text}"
            await bot.send_message(ADMIN_ID, caption)
        elif message.photo:
            await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption)
        elif message.document:
            await bot.send_document(ADMIN_ID, message.document.file_id, caption=caption)
        else:
            await bot.send_message(ADMIN_ID, caption + "\n[Пользователь отправил нераспознанный тип сообщения]")

        await message.answer("Спасибо! Мы получили ваш заказ. Менеджер скоро свяжется с вами.💬")
        waiting_for_order.remove(user_id)
        return

    # Обработка запроса оператора
    if "оператор" in text:
        await message.answer("Оператор скоро свяжется с Вами. Спасибо за обращение!🫂")
        await bot.send_message(
            ADMIN_ID,
            f"📩 Запрос к оператору!\n"
            f"Имя: {message.from_user.full_name}\n"
            f"Username: @{message.from_user.username or 'нет'}\n"
            f"Сообщение: {message.text if message.text else 'Пользователь отправил медиа-файл'}"
        )
        return

    # Поиск ответа в FAQ (только для текстовых сообщений)
    if message.text:
        response = find_best_match(text)
        if response:
            await message.answer(response)
            return

    # Ответ по умолчанию
    await message.answer("Извините, я не нашёл ответа на этот вопрос. Напишите слово 'оператор' для связи с менеджером.")

async def main():
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
