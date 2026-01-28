#!/usr/bin/env python3
# test_main.py - Main.py ni test qilish

import asyncio
import config
import database
from userbot import UserBot

async def test_basic():
    print("1. Database test...")
    await database.setup_database()
    print("✅ Database OK")
    
    print("2. Userbot test...")
    userbot = UserBot()
    try:
        success = await userbot.start()
        if success:
            print("✅ Userbot OK")
        else:
            print("⚠️ Userbot ishlamadi")
    except Exception as e:
        print(f"❌ Userbot xatosi: {e}")
    
    print("3. Test tugadi")

if __name__ == "__main__":
    asyncio.run(test_basic())