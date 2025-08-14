import os
import re
import asyncio
from aiogram import Bot, Dispatcher, types

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192  # Твой Telegram ID (число)

# Храним список пользователей, от которых ждём сообщение по заказу
waiting_for_order = set()

# Список частых вопросов
FAQ = {
    r"(сдела.*|заказ.*)": "Для заказа напишите слово 'оператор' в бот. Менеджер с Вами свяжется.",
    r"(сколь.*|стои.*|доставк.*|цена.*)": "Стоимость доставки рассчитывается индивидуально исходя из плотности и веса груза. Напишите боту слово 'оператор', и менеджер с вами свяжется.",
    r"(время.*|срок.*|когда.*придет.*|через.*дней.*|сроки.*)": "Сроки доставки быстрым авто: 10-15 дней, медленным авто: 15-20 дней. (Сроки доставки указаны до рынка Южные Ворота в г.Москва.)"
}

# Поиск лучшего совпадения по ключевым словам
def find_best_match(user_text):
    user_text = user_text.lower()
    best_match = None
    best_score = 0
    for pattern, answer in FAQ.items():
        match = re.findall(pattern, user_text)
        if match:
            score = sum(len(m) for m in match)
            if score > best_score:
                best_score = score
                best_match = answer
    return best_match

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "Привет! Напиши свой вопрос, а я постараюсь найти на него ответ.\n"
        "Например: 'Сколько стоит доставка?' или 'Как сделать заказ?'\n"
        "Если нужен живой человек — напиши слово 'оператор'.\n"
        "Чтобы оформить заказ — выберете /заказ в меню."
    )

@dp.message_handler(commands=['/buy'])
async def ask_order(message: types.Message):
    user_id = message.from_user.id
    waiting_for_order.add(user_id)
    await message.answer("Расскажите, что вы хотите заказать? В каком количестве?")

@dp.message_handler()
async def search_answer(message: types.Message):
    user_id = message.from_user.id
    text = message.text.lower()

    # Если ждём от пользователя сообщение по заказу
    if user_id in waiting_for_order:
        await bot.send_message(
            ADMIN_ID,
            f"📦 Новый заказ!\n"
            f"Имя: {message.from_user.full_name}\n"
            f"Username: @{message.from_user.username if message.from_user.username else 'нет'}\n"
            f"Заказ: {message.text}"
        )
        await message.answer("Спасибо! Мы получили ваш заказ. Менеджер скоро свяжется с вами.")
        waiting_for_order.remove(user_id)
        return

    # Если пользователь просит оператора
    if "оператор" in text:
        await message.answer("Оператор скоро свяжется с Вами. Спасибо за обращение!")
        await bot.send_message(
            ADMIN_ID,
            f"📩 Запрос к оператору!\n"
            f"Имя: {message.from_user.full_name}\n"
            f"Username: @{message.from_user.username if message.from_user.username else 'нет'}\n"
            f"Сообщение: {message.text}"
        )
        return

    # Поиск ответа в FAQ
    response = find_best_match(text)
    if response:
        await message.answer(response)
    else:
        await message.answer("Извини, я не нашёл ответа на этот вопрос. Чтобы связаться с менеджером, напишите слово 'оператор'.")

if __name__ == "__main__":
    asyncio.run(dp.start_polling())
