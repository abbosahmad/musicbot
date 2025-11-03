import asyncio
import os
import random
from typing import Dict, List

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand, FSInputFile, InputMediaPhoto, InputMediaVideo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from pydub import AudioSegment

import config
import database
import utils
from userbot import UserBot

logger.add("bot_logs.log", rotation="1 week", retention="1 month", level="INFO", encoding="utf-8")
bot_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
bot = Bot(token=config.ADMIN_BOT_TOKEN, default=bot_properties)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
userbot = UserBot()

daily_plan: List[Dict] = []
PROCESSING_LOCK = asyncio.Lock()


async def log_to_channel(text: str):
    try:
        await bot.send_message(config.LOG_CHANNEL_ID, text)
    except Exception as e:
        logger.error(f"Log kanaliga xabar yuborishda xatolik: {e}")


async def post_music(track_info: Dict):
    track_id = track_info.get('track_id', 'unknown')
    
    raw_artist = track_info.get('artist')
    raw_title = track_info.get('title')
    
    # 1. Yordamchi `utils` fayli yordamida ijrochi va nomni aqlli tahlil qilib, ajratib olamiz.
    parsed_artist, parsed_title = utils._parse_artist_and_title(raw_artist, raw_title)
    
    # 2. Topilgan ma'lumotlarni keraksiz so'zlardan tozalaymiz.
    cleaned_artist_for_meta = utils._clean_single_string(parsed_artist)
    cleaned_title_for_meta = utils._clean_single_string(parsed_title)

    # 3. Agar tozalashdan so'ng ijrochi nomi bo'shab qolsa yoki juda qisqa bo'lsa, uning o'rniga "Music" so'zini yozamiz.
    if not cleaned_artist_for_meta or len(cleaned_artist_for_meta) < 2:
        cleaned_artist_for_meta = "Music"
    
    # Agar sarlavha bo'shab qolsa, original nomni tozalab ishlatamiz.
    if not cleaned_title_for_meta:
        cleaned_title_for_meta = utils._clean_single_string(raw_title)

    # 4. Ma'lumotlar bazasiga ham aynan shu TOZA ma'lumotlarni yozamiz.
    await database.add_track_to_db(track_id, cleaned_artist_for_meta, cleaned_title_for_meta)
    
    async with PROCESSING_LOCK:
        duration_sec = track_info.get('duration_ms', 0) / 1000
        
        # 5. Fayl nomi uchun alohida chiroyli formatlaymiz.
        filename_text = utils.clean_title(raw_title, raw_artist)
        
        os.makedirs("downloads", exist_ok=True)
        base_temp_filename = f"temp_{track_id}_{random.randint(1000, 9999)}"
        temp_audio_path = os.path.join("downloads", f"{base_temp_filename}.mp3")
        temp_demo_path = os.path.join("downloads", f"{base_temp_filename}_demo.ogg")
        
        downloaded_file_path = None
        try:
            logger.info(f"'{filename_text}' uchun yuklash boshlandi...")
            downloaded_file_path = await userbot.download_music(
                chat_id=track_info['chat_id'],
                message_id=track_info['message_id'],
                file_path=temp_audio_path
            )
            
            if not downloaded_file_path:
                raise Exception("Faylni yuklab bo'lmadi yoki fayl bo'sh.")
            logger.success(f"'{filename_text}' diskka muvaffaqiyatli yuklandi.")

            reply_to_msg_id = None
            try:
                if hasattr(config, 'DEMO_DURATION_SECONDS') and duration_sec > 90:
                    main_audio = AudioSegment.from_file(downloaded_file_path)
                    safe_duration = max(0, int(duration_sec) - config.DEMO_DURATION_SECONDS - 10)
                    start_sec = random.randint(30, safe_duration) if safe_duration > 30 else 30
                    start_cut_ms = start_sec * 1000
                    end_cut_ms = start_cut_ms + (config.DEMO_DURATION_SECONDS * 1000)
                    demo_audio = main_audio[start_cut_ms:end_cut_ms]
                    demo_audio.export(temp_demo_path, format="ogg", codec="libopus")
                    demo_msg = await bot.send_voice(config.MAIN_CHANNEL_ID, voice=FSInputFile(temp_demo_path))
                    reply_to_msg_id = demo_msg.message_id
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Demo yaratishda xatolik: {e}")
            
            final_caption = (f"👇 Obuna bo'ling 👇\n"
                             f"<a href='{config.MAIN_CHANNEL_LINK}'>Trend MUSIC 🔥❤️</a>")

            await bot.send_audio(
                config.MAIN_CHANNEL_ID,
                audio=FSInputFile(downloaded_file_path, filename=f"{filename_text}.mp3"),
                caption=final_caption,
                duration=int(duration_sec),
                performer=cleaned_artist_for_meta,
                title=cleaned_title_for_meta,
                thumbnail=FSInputFile("thumbnail.jpg"),
                reply_to_message_id=reply_to_msg_id
            )
            
            logger.success(f"'{filename_text}' kanalga muvaffaqiyatli yuborildi.")
            await log_to_channel(f"✅ Musiqa yuborildi: {filename_text}")

        except Exception as e:
            logger.error(f"Musiqani yuborishda global xatolik ({filename_text}): {e}")
            await log_to_channel(f"❌ Musiqani yuborishda xatolik: {filename_text}\nSabab: {e}")
        finally:
            if downloaded_file_path and os.path.exists(downloaded_file_path): os.remove(downloaded_file_path)
            if os.path.exists(temp_demo_path): os.remove(temp_demo_path)

async def plan_daily_posts():
    global daily_plan
    daily_plan.clear()
    logger.info("--- KUNLIK REJALASHTIRIS BOSHLANDI ---")
    await log_to_channel("🗓️ Yangi kun uchun kontent qidirilmoqda...")
    tracks_for_planning = await userbot.get_new_music_from_channels()
    if not tracks_for_planning:
        await log_to_channel("⚠️ Manba kanallarda yangi musiqa topilmadi, zaxiradan qidirilmoqda...")
        tracks_for_planning = await userbot.get_recent_music_from_backup(hours=48)
    if not tracks_for_planning:
        await log_to_channel("⚠️ Zaxira kanalda ham yangi musiqa topilmadi, manbalarning eski tarixidan qidirilmoqda...")
        tracks_for_planning = await userbot.get_old_music_from_sources()
    if tracks_for_planning:
        random.shuffle(tracks_for_planning)
        posts_for_today_count = utils.get_daily_post_count()
        tracks_for_today = tracks_for_planning[:posts_for_today_count]
        post_times = utils.calculate_post_times(len(tracks_for_today))
        for i, track in enumerate(tracks_for_today):
            scheduler.add_job(post_music, 'date', run_date=post_times[i], args=[track])
            daily_plan.append({'title': utils.clean_title(track['title'], track['artist']), 'time': post_times[i].strftime('%H:%M')})
        plan_text = f"✅ Kunlik reja tuzildi ({len(tracks_for_today)} ta musiqa):\n\n" + "\n".join([f"🕒 {item['time']} - {item['title']}" for item in daily_plan])
        await log_to_channel(plan_text)
        surplus_tracks = tracks_for_planning[posts_for_today_count:]
        if surplus_tracks: await userbot.forward_tracks_to_backup(surplus_tracks)
    else:
        logger.error("Bugun uchun yuborishga umuman musiqa topilmadi (barcha manbalar tekshirildi)!")
        await log_to_channel("❌ Bugun uchun yuborishga umuman musiqa topilmadi.")
    logger.info("--- KUNLIK REJALASHTIRISH TUGADI ---")

async def post_daily_album():
    logger.info("Albom uchun media qidirilmoqda...")
    try:
        photos, video = [], None
        async for message in userbot.app.get_chat_history(config.BACKUP_CHANNEL_ID, limit=50):
            if message.photo and len(photos) < 3:
                photos.append(InputMediaPhoto(media=message.photo.file_id))
            if message.video and not video:
                video = InputMediaVideo(media=message.video.file_id)
            if len(photos) == 3 and video: break
        if len(photos) < 3 or not video:
            logger.warning("Albom uchun yetarli media topilmadi (3 rasm va 1 video kerak).")
            return
        photos.reverse()
        video.caption = (f"🔥 Haftaning eng sara to'plami!\n\n👇 Obuna bo'ling 👇\n<a href='{config.MAIN_CHANNEL_LINK}'>{config.MAIN_CHANNEL_NAME}</a>")
        media_group = [video] + photos
        await bot.send_media_group(config.MAIN_CHANNEL_ID, media=media_group)
        logger.success("Kunlik albom muvaffaqiyatli yuborildi.")
        await log_to_channel("✅ Kunlik albom yuborildi.")
    except Exception as e:
        logger.error(f"Albom yuborishda xatolik: {e}")
        await log_to_channel(f"❌ Albom yuborishda xatolik: {e}")

@dp.message(Command("start", "holat"))
async def start_command(message: types.Message):
    if message.from_user.id != config.ADMIN_USER_ID: return
    text = "Bot ishlamoqda. Bugungi reja:\n\n"
    if not daily_plan: text += "Hali reja tuzilmagan. /rejalash buyrug'ini yuboring."
    else: text += "\n".join([f"🕒 {item['time']} - {item['title']}" for item in daily_plan])
    await message.answer(text)

@dp.message(Command("rejalash"))
async def force_plan(message: types.Message):
    if message.from_user.id != config.ADMIN_USER_ID: return
    try:
        await message.answer("🔄 Kunlik rejalashtirish majburan ishga tushirildi...")
        await plan_daily_posts()
        await message.answer("✅ Rejalashtirish yakunlandi. Natijalarni /holat orqali tekshiring.")
    except Exception as e: logger.error(f"`/rejalash` buyrug'ida xatolik: {e}")

@dp.message(Command("kanaldan"))
async def force_post_from_channel(message: types.Message):
    if message.from_user.id != config.ADMIN_USER_ID: return
    try:
        await message.answer("🔄 Manba kanallardan yangi musiqa qidirilmoqda...")
        channel_music = await userbot.get_new_music_from_channels()
        if channel_music:
            track_to_post = random.choice(channel_music)
            await message.answer(f"✅ Trek topildi: {utils.clean_title(track_to_post['title'], track_to_post['artist'])}. Yuborilmoqda...")
            await post_music(track_to_post)
        else: await message.answer("❌ Manba kanallarda yuborish uchun YANGI musiqa topilmadi.")
    except Exception as e: logger.error(f"`/kanaldan` buyrug'ida xatolik: {e}")

async def set_main_menu(bot: Bot):
    main_menu_commands = [
        BotCommand(command="/start", description="🚀 Bot holati va bugungi reja"),
        BotCommand(command="/rejalash", description="🗓️ Kunlik rejani yangilash"),
        BotCommand(command="/kanaldan", description="📢 Kanaldan musiqa joylash")]
    await bot.set_my_commands(main_menu_commands)

async def setup_scheduler():
    scheduler.add_job(plan_daily_posts, 'cron', hour=config.PLANNING_HOUR, minute=0)
    scheduler.add_job(post_daily_album, 'cron', day='*/2', hour=20, minute=0)
    scheduler.start()
    logger.info("Rejalashtiruvchi (scheduler) ishga tushirildi.")

async def on_startup(bot: Bot):
    await set_main_menu(bot)
    await database.setup_database()
    await userbot.start()
    await setup_scheduler()
    await log_to_channel("🚀 Bot ishga tushdi va barcha modullar sozlandi!")

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot o'chirildi.")