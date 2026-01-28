#!/usr/bin/env python3
# main_simple.py - Sodda versiya test uchun

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import config

# Bot sozlamalari
bot_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
bot = Bot(token=config.ADMIN_BOT_TOKEN, default=bot_properties)
dp = Dispatcher()

async def main():
    print(">>> Sodda bot ishga tushirilmoqda...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        print(f"Xato: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot o'chirildi.")