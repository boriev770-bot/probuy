import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import init_db, add_user, get_user_code, add_track, get_tracks

TOKEN = os.getenv("BOT_TOKEN")  # <-- на Railway укажешь переменную BOT_TOKEN
WAREHOUSE_CHAT_ID = os.getenv("WAREHOUSE_CHAT_ID")  # <-- ID чата сотрудника склада

bot = Bot(token=7559588518:AAEv5n_8N_gGo97HwpZXDHTi3EQ40S1aFcI)
dp = Dispatcher(7095008192)

# FSM состояния
class TrackForm(StatesGroup):
    waiting_for_delivery = State()
    waiting_for_track = State()


# Старт
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привет! Я помогу оформить доставку. Используй /getcod чтобы получить личный номер.")


# Получение кода
@dp.message(Command("getcod"))
async def getcod(message: types.Message):
    code = get_user_code(message.from_user.id)
    if code:
        await message.answer(f"Ваш код уже присвоен: {code}")
    else:
        # Создаём новый
        new_code = "PR" + str(message.from_user.id).zfill(5)[-5:]
        add_user(message.from_user.id, new_code)
        await message.answer(f"Вам присвоен личный номер: {new_code}")


# Адрес склада
@dp.message(Command("adress"))
async def adress(message: types.Message):
    warehouse_address = "📦 Китай, Гуанчжоу, ул. Примерная, д. 1"  # <-- здесь впишешь реальный адрес
    await message.answer(f"Адрес склада:\n{warehouse_address}")


# Отправка трека
@dp.message(Command("sendtrack"))
async def sendtrack(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Быстрое авто"), KeyboardButton(text="🚙 Медленное авто")],
            [KeyboardButton(text="✈ Авиа"), KeyboardButton(text="🚂 ЖД")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите способ доставки:", reply_markup=keyboard)
    await state.set_state(TrackForm.waiting_for_delivery)


@dp.message(TrackForm.waiting_for_delivery)
async def choose_delivery(message: types.Message, state: FSMContext):
    await state.update_data(delivery=message.text)
    await message.answer("Теперь введите ваш трек номер:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(TrackForm.waiting_for_track)


@dp.message(TrackForm.waiting_for_track)
async def get_track(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    delivery = user_data["delivery"]
    track = message.text

    add_track(message.from_user.id, track, delivery)

    code = get_user_code(message.from_user.id)
    history = get_tracks(message.from_user.id)
    history_text = "\n".join([f"{t[0]} ({t[1]})" for t in history])

    await message.answer(f"✅ Трек {track} ({delivery}) сохранён.\n\nИстория ваших треков:\n{history_text}")

    # Отправка на склад
    if WAREHOUSE_CHAT_ID:
        await bot.send_message(
            WAREHOUSE_CHAT_ID,
            f"📦 Новый трек!\nПользователь: {message.from_user.id} ({code})\nТрек: {track}\nДоставка: {delivery}"
        )

    await state.clear()


# Просмотр всех треков
@dp.message(Command("mytracks"))
async def mytracks(message: types.Message):
    history = get_tracks(message.from_user.id)
    if not history:
        await message.answer("У вас пока нет треков.")
    else:
        text = "\n".join([f"{t[0]} ({t[1]})" for t in history])
        await message.answer(f"📋 Ваши треки:\n{text}")


# Запуск
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
