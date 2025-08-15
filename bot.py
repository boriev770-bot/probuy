import os
import re
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

TOKEN = "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI"
ADMIN_ID = 7095008192  # ID администратора
WAREHOUSE_ID = ВСТАВЬ_ID_СКЛАДА  # ID сотрудника склада

DATA_FILE = "data.json"

FAQ = {
    r"(сдела.*|заказ.*)": "Для заказа напишите слово 'оператор' в бот. Менеджер с вами свяжется.",
    r"(сколь.*|стои.*|доставк.*|цена.*доставк.*)": "Стоимость доставки рассчитывается индивидуально. Напишите слово 'оператор' и менеджер свяжется.",
    r"(время.*|срок.*|когда.*придет.*|через.*дней.*|сроки.*доставк.*)": "Сроки доставки быстрым авто: 10-15 дней, медленным авто: 15-20 дней."
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
    await message.answer("Привет! Напиши свой вопрос или используй команды:
"
                         "/getcod — получить личный номер
"
                         "/adress — адрес склада
"
                         "/sendtrack — отправить трек
"
                         "Если нужен оператор — напиши 'оператор'."
                        )

@dp.message_handler(commands=['getcod'])
async def get_code(message: types.Message):
    data = load_data()
    user_id = str(message.from_user.id)
    if user_id not in data:
        last_number = max([int(v['code'][2:]) for v in data.values()] or [0])
        new_code = f"PR{last_number+1:05d}"
        data[user_id] = {"code": new_code, "tracks": []}
        save_data(data)
        await message.answer(f"Ваш личный номер: {new_code}")
    else:
        await message.answer(f"Ваш личный номер: {data[user_id]['code']}")

@dp.message_handler(commands=['adress'])
async def adress(message: types.Message):
    await message.answer("ВСТАВЬ_СВОЙ_АДРЕС_СКЛАДА")

@dp.message_handler(commands=['sendtrack'])
async def send_track(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🚗 Быстрое авто"), KeyboardButton("🚛 Медленное авто"))
    await message.answer("Выберите способ доставки:", reply_markup=kb)

@dp.message_handler(lambda m: m.text in ["🚗 Быстрое авто", "🚛 Медленное авто"])
async def get_delivery_type(message: types.Message):
    delivery_type = message.text
    await message.answer("Отправьте трек-номер:", reply_markup=types.ReplyKeyboardRemove())
    dp.delivery_choice = delivery_type

@dp.message_handler()
async def text_handler(message: types.Message):
    text = message.text.lower()

    if text == "оператор":
        await message.answer("Оператор скоро свяжется с вами.")
        await bot.send_message(ADMIN_ID,
                               f"📩 Запрос к оператору!
Имя: {message.from_user.full_name}
"
                               f"Username: @{message.from_user.username or 'нет'}
"
                               f"Сообщение: {message.text}")
        return

    if hasattr(dp, "delivery_choice"):
        data = load_data()
        user_id = str(message.from_user.id)
        if user_id not in data:
            await message.answer("Сначала получите личный номер через /getcod")
            return
        data[user_id]["tracks"].append({"track": message.text, "delivery": dp.delivery_choice})
        save_data(data)
        await bot.send_message(WAREHOUSE_ID,
                               f"📦 Новый трек!
Код клиента: {data[user_id]['code']}
"
                               f"Трек: {message.text}
Способ доставки: {dp.delivery_choice}")
        await message.answer("Трек отправлен на склад.")
        del dp.delivery_choice
        return

    response = find_best_match(text)
    if response:
        await message.answer(response)
    else:
        await message.answer("Не понял вопрос. Напиши 'оператор' для связи.")

if __name__ == "__main__":
    asyncio.run(dp.start_polling())
