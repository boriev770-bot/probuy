import os
import re
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Конфигурация
TOKEN = os.getenv("TOKEN", "7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7095008192"))
WAREHOUSE_ID = int(os.getenv("WAREHOUSE_ID", "123456789"))
WAREHOUSE_ADDRESS = os.getenv(
    "WAREHOUSE_ADDRESS",
    "ТУТ_УКАЖИ_АДРЕС_СКЛАДА_В_КИТАЕ\nПолучатель: ...\nТелефон: ...\nАдрес: ..."
)

CLIENTS_FILE = "clients.json"

# Загрузка базы клиентов
if not os.path.exists(CLIENTS_FILE):
    with open(CLIENTS_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

def load_clients():
    with open(CLIENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_clients(data):
    with open(CLIENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# FAQ
FAQ = {
    r"(сдела.*|заказ.*)": "Для заказа напишите слово 'оператор' в бот. Менеджер с Вами свяжется.",
    r"(сколь.*|стои.*|доставк.*цена.*|цена.*доставк.*)": "Стоимость доставки рассчитывается индивидуально исходя из плотности и веса груза. Напишите боту слово 'оператор' и менеджер с вами свяжется",
    r"(время.*|срок.*|когда.*придет.*|через.*дней.*|сроки.*доставк.*)": "Сроки доставки: быстрое авто — 10-15 дней, медленное авто — 15-20 дней (до рынка Южные Ворота, Москва)."
}

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
        "Команды:\n"
        "/getcod — получить личный код\n"
        "/adress — адрес склада\n"
        "/sendtrack — отправить трек-номер\n"
        "/manager — вызвать оператора"
    )

@dp.message_handler(commands=['getcod'])
async def getcod(message: types.Message):
    clients = load_clients()
    user_id = str(message.from_user.id)
    if user_id in clients and "code" in clients[user_id]:
        code = clients[user_id]["code"]
    else:
        last_num = max([int(v["code"][2:]) for v in clients.values() if "code" in v] or [0])
        new_num = last_num + 1
        code = f"PR{new_num:05d}"
        clients[user_id] = {"code": code, "tracks": []}
        save_clients(clients)
    await message.answer(f"Ваш личный код: {code}")

@dp.message_handler(commands=['adress'])
async def adress(message: types.Message):
    await message.answer(f"📦 Адрес склада в Китае:\n{WAREHOUSE_ADDRESS}")

@dp.message_handler(commands=['sendtrack'])
async def sendtrack(message: types.Message):
    await message.answer("✏️ Отправьте трек-номер вашего заказа:")
    dp.register_message_handler(get_track, state=None)

async def get_track(message: types.Message):
    track = message.text.strip()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Быстрое авто"), KeyboardButton("Медленное авто"))
    await message.answer("Выберите способ доставки:", reply_markup=kb)
    dp.register_message_handler(lambda m: get_delivery_method(m, track), state=None)

async def get_delivery_method(message: types.Message, track):
    delivery = message.text.strip()
    clients = load_clients()
    user_id = str(message.from_user.id)
    if user_id not in clients:
        await message.answer("Сначала получите личный код с помощью /getcod")
        return
    code = clients[user_id]["code"]
    clients[user_id]["tracks"].append({"track": track, "delivery": delivery})
    save_clients(clients)

    await bot.send_message(
        WAREHOUSE_ID,
        f"📦 Новый трек для сборки:\nКод клиента: {code}\nТрек: {track}\nДоставка: {delivery}"
    )
    await message.answer("✅ Трек-номер отправлен на склад.", reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(commands=['manager'])
async def manager(message: types.Message):
    await message.answer("Оператор скоро свяжется с вами.")
    await bot.send_message(
        ADMIN_ID,
        f"📩 Запрос к оператору!\nИмя: {message.from_user.full_name}\nUsername: @{message.from_user.username or 'нет'}\nСообщение: /manager"
    )

@dp.message_handler(commands=['broadcast'])
async def broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("Введите текст после команды /broadcast")
        return
    clients = load_clients()
    for uid in clients.keys():
        try:
            await bot.send_message(uid, text)
        except:
            pass
    await message.answer("✅ Рассылка завершена.")

@dp.message_handler()
async def search_answer(message: types.Message):
    text = message.text.lower()
    if "оператор" in text:
        await message.answer("Оператор скоро свяжется с Вами.")
        await bot.send_message(
            ADMIN_ID,
            f"📩 Запрос к оператору!\nИмя: {message.from_user.full_name}\nUsername: @{message.from_user.username or 'нет'}\nСообщение: {message.text}"
        )
        return
    response = find_best_match(text)
    if response:
        await message.answer(response)
    else:
        await message.answer("Извини, я не нашёл ответа на этот вопрос. Чтобы связаться с менеджером, напишите 'оператор'.")

if __name__ == '__main__':
    asyncio.run(dp.start_polling())
