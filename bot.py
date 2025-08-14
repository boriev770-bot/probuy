import os
import re
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import asyncio

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"

# FAQ: ключевые слова (regex) -> ответ
FAQ = {
    r"(сдела.*|заказ.*)": "Для заказа напишите нам в телеграм @probuykmvadmin",
    r"(сколь.*|стои.*|доставк.*)": "Стоимость доставки рассчитывается индивидуально исходя из плотности, веса груза. Напишите нам @probuykmvadmin и мы предоставим подробный расчет стоимости."
    }

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
    text = message.text.lower()
    for pattern, answer in FAQ.items():
        if re.search(pattern, text):
            await message.answer(answer)
            return
    await message.answer("Извини, я не нашёл ответа на этот вопрос.")

if __name__ == '__main__':
    asyncio.run(executor.start_polling(dp))
