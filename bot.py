python
import asyncio
import os
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart
from dotenv import load_dotenv

# Load environment variables untuk testing lokal
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SONAUTO_API_KEY = os.getenv("SONAUTO_API_KEY")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()

# State Management (FSM)
class SongGeneration(StatesGroup):
    waiting_for_prompt = State()
    waiting_for_lyrics = State()

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Create Song", callback_data="cmd_new")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="cmd_settings"),
         InlineKeyboardButton(text="👤 Account", callback_data="cmd_account")]
    ])

def get_mode_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎙️ Auto Vocals", callback_data="mode_auto")],
        [InlineKeyboardButton(text="📝 Custom Lyrics", callback_data="mode_custom")],
        [InlineKeyboardButton(text="🎸 Instrumental", callback_data="mode_instrumental")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cmd_cancel")]
    ])

@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    teks = (
        f"Welcome to **Sonauto AI**, {message.from_user.first_name}!\n\n"
        "Generate high-quality music from text prompts instantly.\n"
        "Tap the button below to start."
    )
    await message.answer(teks, reply_markup=get_main_menu(), parse_mode='Markdown')

@router.callback_query(F.data == "cmd_new")
async def ask_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SongGeneration.waiting_for_prompt)
    await callback.message.edit_text(
        "🎧 *Step 1: Track Description*\n\n"
        "Describe the genre, vibe, or style of the song.",
        parse_mode='Markdown'
    )

@router.callback_query(F.data == "cmd_cancel")
async def cancel_process(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Generation cancelled.")
    await callback.message.answer("Main Menu:", reply_markup=get_main_menu())

@router.message(SongGeneration.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    await message.answer(
        "✅ *Prompt saved.*\n\nChoose your vocal mode:",
        reply_markup=get_mode_menu(), parse_mode='Markdown'
    )

@router.callback_query(F.data.startswith("mode_"))
async def process_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split("_")[1]
    await state.update_data(mode=mode)

    if mode == "custom":
        await state.set_state(SongGeneration.waiting_for_lyrics)
        await callback.message.edit_text("📝 Send your custom lyrics now:")
    else:
        await callback.message.edit_text("⏳ Initializing AI Engine...")
        await generate_and_send(callback.message, state)

@router.message(SongGeneration.waiting_for_lyrics)
async def process_custom_lyrics(message: Message, state: FSMContext):
    await state.update_data(lyrics=message.text)
    msg = await message.answer("⏳ Lyrics received. Initializing AI Engine...")
    await generate_and_send(msg, state)

async def generate_and_send(message: Message, state: FSMContext):
    user_data = await state.get_data()
    prompt = user_data.get("prompt")
    mode = user_data.get("mode")
    lyrics = user_data.get("lyrics")
    
    await state.clear()
    
    loading_msg = await message.edit_text("⬛⬛⬛⬛⬛ 10% - Submitting task...")
    
    payload = {"prompt": prompt}
    if mode == "instrumental":
        payload["instrumental"] = True
    elif mode == "custom" and lyrics:
        payload["lyrics"] = lyrics

    headers = {
        "Authorization": f"Bearer {SONAUTO_API_KEY}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            # 1. POST untuk mendapatkan Task ID
            async with session.post("https://api.sonauto.ai/v1/generations/v3", json=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                task_id = data.get("task_id")
                
            if not task_id:
                await loading_msg.edit_text("❌ Error: No Task ID returned by server.")
                return

            await loading_msg.edit_text(f"🟨🟨⬛⬛⬛ 30% - Queued (ID: `{task_id[:8]}`)...", parse_mode='Markdown')
            
            # 2. Polling loop mengecek status
            max_retries = 60 # Maksimal 5 menit
            for attempt in range(max_retries):
                await asyncio.sleep(5)
                
                async with session.get(f"https://api.sonauto.ai/v1/generations/status/{task_id}", headers=headers) as poll_resp:
                    poll_resp.raise_for_status()
                    poll_data = await poll_resp.json()
                    status = poll_data.get("status", "").lower()
                    
                    if status == "completed":
                        await loading_msg.edit_text("🟩🟩🟩🟩🟩 99% - Finalizing audio...")
                        
                        audio_url = poll_data.get("audio_url") or poll_data.get("url") or poll_data.get("file_url")
                        
                        if audio_url:
                            audio_file = URLInputFile(audio_url)
                            caption = f"🎵 *Track Complete*\n\n*Prompt:* {prompt}"
                            
                            await message.bot.send_audio(
                                chat_id=message.chat.id,
                                audio=audio_file,
                                caption=caption,
                                parse_mode='Markdown'
                            )
                            await loading_msg.delete()
                        else:
                            await loading_msg.edit_text("✅ Status completed, but no audio link provided.")
                        return
                        
                    elif status in ["failed", "failure", "error"]:
                        await loading_msg.edit_text(f"❌ Generation failed at Sonauto server. Status: `{status}`", parse_mode='Markdown')
                        return
                    
                    else:
                        if attempt % 3 == 0:
                            await loading_msg.edit_text(f"🟨🟨🟨🟨⬛ 70% - Rendering audio... (Check {attempt+1})")

            await loading_msg.edit_text("⏳ Request timed out (5 minutes). Please try again.")
                
        except Exception as e:
            await loading_msg.edit_text(f"❌ HTTP Communication Error:\n`{e}`", parse_mode='Markdown')

async def main():
    dp.include_router(router)
    print("Sonauto Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
