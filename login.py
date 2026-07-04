# login.py

import asyncio
import os
from pyrogram import Client
import config

async def main():
    print("Userbot uchun sessiya yaratish boshlandi...")
    os.makedirs("session", exist_ok=True)

    print("Iltimos, Telegramga ulangan telefon raqamingizni kiriting (masalan, +998901234567):")
    
    async with Client("session/my_account", api_id=config.USERBOT_API_ID, api_hash=config.USERBOT_API_HASH) as app:
        session_str = await app.export_session_string()
        await app.send_message("me", "Userbot sessiyasi muvaffaqiyatli yaratildi!")
        
        print("\n--- Muvaffaqiyatli! ---")
        print("!!! DIQQAT: Quyidagi sessiya satrini nusxalab, .env faylidagi USERBOT_SESSION_STRING o'zgaruvchisiga yozib qo'ying:\n")
        print(session_str)
        print("\n-----------------------\n")

if __name__ == "__main__":
    asyncio.run(main())