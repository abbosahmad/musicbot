#!/usr/bin/env python3
# test_userbot.py - Userbot ulanishini test qilish

import asyncio
import config
from pyrogram import Client

async def test_userbot():
    print("Userbot test qilinmoqda...")
    
    try:
        app = Client(
            name="session/test_session",
            api_id=config.USERBOT_API_ID,
            api_hash=config.USERBOT_API_HASH,
            session_string=config.USERBOT_SESSION_STRING
        )
        
        print("Ulanmoqda...")
        await app.start()
        
        me = await app.get_me()
        print(f"✅ Muvaffaqiyat! Userbot: @{me.username} ({me.first_name})")
        
        # Birinchi manba kanalini tekshirish
        if config.SOURCE_CHANNELS:
            test_channel = config.SOURCE_CHANNELS[0]
            print(f"Test kanal: {test_channel}")
            
            try:
                chat = await app.get_chat(test_channel)
                print(f"✅ Kanal topildi: {chat.title}")
                
                # Oxirgi 10 ta xabarni olish
                messages = []
                async for message in app.get_chat_history(test_channel, limit=10):
                    if message.audio or message.voice:
                        messages.append(message)
                
                print(f"✅ Oxirgi 10 xabardan {len(messages)} tasi musiqa")
                
            except Exception as e:
                print(f"❌ Kanal xatosi: {e}")
        
        await app.stop()
        
    except Exception as e:
        print(f"❌ Xatolik: {e}")

if __name__ == "__main__":
    asyncio.run(test_userbot())