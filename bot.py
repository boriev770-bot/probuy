import re
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import asyncio

TOKEN = "ВСТАВЬ_СВОЙ_ТОКЕН"

# FAQ: ключевые слова (regex) -> ответ
FAQ = {
    # Пример:
    # r"(где.*наход.*)": "Мы находимся в г. Ессентуки, ул. Примерная, 1.",
}

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "Привет! Напиши свой вопрос, а я постараюсь найти на него ответ.\n"
        "Например: 'Сколько стоит доставка?' или 'Где вы находитесь?'"
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
