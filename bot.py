import asyncio
import os
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart

# Ambil dari Environment Variables langsung
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SONAUTO_API_KEY = os.environ.get("SONAUTO_API_KEY")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()

class SongGeneration(StatesGroup):
    waiting_for_prompt = State()
    waiting_for_lyrics = State()

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Create Song", callback_data="cmd_new")]
    ])

@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Welcome! Press below to start:", reply_markup=get_main_menu())

@router.callback_query(F.data == "cmd_new")
async def ask_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SongGeneration.waiting_for_prompt)
    await callback.message.edit_text("Describe your song:")

@router.message(SongGeneration.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    await state.clear()
    msg = await message.answer("Generating...")
    
    # Langsung panggil fungsi generate sederhana
    headers = {"Authorization": f"Bearer {SONAUTO_API_KEY}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post("[https://api.sonauto.ai/v1/generations/v3](https://api.sonauto.ai/v1/generations/v3)", json={"prompt": message.text}, headers=headers) as resp:
            data = await resp.json()
            task_id = data.get("task_id")
            await msg.edit_text(f"Task created: {task_id}")

async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
