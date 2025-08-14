import os
import re
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# Токен бота
TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"

# FAQ: ключевые слова (regex) -> ответ
FAQ = {
    r"(сдела.*|заказ.*)": "Для заказа напишите нам в телеграм @probuykmvadmin",
    r"(сколь.*|стои.*|доставк.*цена.*|цена.*доставк.*)": "Стоимость доставки рассчитывается индивидуально исходя из плотности, веса груза. Напишите нам @probuykmvadmin и мы предоставим подробный расчет стоимости.",
    r"(время.*|срок.*|когда.*придет.*|через.*дней.*|сроки.*доставк.*)": "Сроки доставки быстрым авто: 10-15 дней, медленным авто: 15-20 дней. (Сроки доставки указаны до рынка Южные Ворота в г.Москва.)"
}

# Функция умного поиска
def find_best_match(user_text):
    user_text = user_text.lower()
    best_match = None
    best_score = 0

    for pattern, answer in FAQ.items():
        match = re.findall(pattern, user_text)
        if match:
            # Чем длиннее найденные совпадения, тем выше оценка
            score = sum(len(m) for m in match)
            if score > best_score:
                best_score = score
                best_match = answer

    return best_match

# Создаем бота и диспетчер
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "Привет! Напиши свой вопрос, а я постараюсь найти на него ответ.\n"
        "Например: 'Сколько стоит доставка?' или 'Как сделать заказ?'"
    )

@dp.message_handler()
async def search_answer(message: types.Message):
    response = find_best_match(message.text)
    if response:
        await message.answer(response)
    else:
        await message.answer("Извини, я не нашёл ответа на этот вопрос. Напиши нам @probuykmvadmin")

if __name__ == '__main__':
    asyncio.run(dp.start_polling())
