import asyncio
import os
import random
import threading
from typing import Dict, List
from datetime import datetime, timedelta

import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand, FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from pydub import AudioSegment

import config
import database
import utils
import webapp
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
        logger.error(f"Log kanaliga yozishda xato (Bot ishlashda davom etadi): {e}")


async def post_music(track_info: Dict):


    track_id = track_info.get('track_id', 'unknown')


    raw_artist = track_info.get('artist') or "Unknown Artist"


    raw_title = track_info.get('title') or "Unknown Track"


    


    if await database.is_track_posted(track_id):


        logger.info(f"Trek {track_id} allaqachon joylangan.")


        return





    async with PROCESSING_LOCK:


        os.makedirs("downloads", exist_ok=True)


        base_filename = f"track_{track_id}_{random.randint(1000, 9999)}"


        temp_dirty_path = os.path.join("downloads", f"{base_filename}_dirty.mp3")


        final_file_path = None


        final_artist = raw_artist


        final_title = raw_title


        


        demo_duration_setting = int(database.get_setting("demo_duration", "30"))





        try:


            logger.info(f"Yangi trek: {raw_artist} - {raw_title}")


            dirty_file = await userbot.download_music(


                track_info['chat_id'], track_info['message_id'], temp_dirty_path


            )


            


            if not dirty_file: raise Exception("Telegramdan yuklab bo'lmadi.")





            # 1. Shazam orqali tekshiramiz


            logger.info("Shazam orqali aniqlanmoqda...")


            shazam_result = await utils.identify_track_with_shazam(dirty_file)


            


            # --- STRATEGIYA BOSHLANDI ---


            


            # A) SHAZAM TOPDI


            if shazam_result:


                shazam_artist = shazam_result['artist']


                shazam_title = shazam_result['title']


                logger.success(f"✅ SHAZAM: {shazam_artist} - {shazam_title}")


                


                # 1. Global Search (Telegram)


                final_file_path = await userbot.search_global_music(shazam_artist, shazam_title)


                


                if final_file_path:


                    final_artist = shazam_artist


                    final_title = shazam_title


                    logger.success("✅ MANBA: Telegram Global Search")


                else:


                    # 2. YouTube (Zaxira)


                    logger.warning("⚠️ Globalda yo'q. YouTube'dan qidirilmoqda...")


                    final_file_path = await utils.get_youtube_with_api(shazam_artist, shazam_title)


                    if final_file_path:


                        final_artist = shazam_artist


                        final_title = shazam_title


                        logger.success("✅ MANBA: YouTube")





            # B) SHAZAM TOPMADI yoki YOUTUBE HAM TOPMADI


            if not final_file_path:


                logger.warning("⚠️ Shazam/YouTube ishlamadi. AI bilan nomini tozalab qidiramiz.")


                


                ai_cleaned = await utils.get_clean_details_with_ai(raw_artist, raw_title)


                clean_artist = ai_cleaned.get('artist', raw_artist)


                clean_title = ai_cleaned.get('title', raw_title)


                


                # 1. Global Search (Tozalangan nom bilan)


                final_file_path = await userbot.search_global_music(clean_artist, clean_title)


                


                if final_file_path:


                    final_artist = clean_artist


                    final_title = clean_title


                    logger.success("✅ MANBA: Telegram Global (AI Cleaned)")


                else:


                    # 2. YouTube (Tozalangan nom bilan)


                    logger.warning("⚠️ Globalda (AI) yo'q. YouTube (AI) qidirilmoqda...")


                    final_file_path = await utils.get_youtube_with_api(clean_artist, clean_title)


                    if final_file_path:


                        final_artist = clean_artist


                        final_title = clean_title


                        logger.success("✅ MANBA: YouTube (AI Cleaned)")





            # --- YAKUNIY TEKSHIRUV ---


            


            if not final_file_path or not os.path.exists(final_file_path):


                logger.error("❌ Barcha manbalar ishlamadi. Post bekor qilindi.")


                if os.path.exists(dirty_file): os.remove(dirty_file)


                await log_to_channel(f"⏭️ O'tkazib yuborildi: {raw_artist} - {raw_title} (Topilmadi)")


                return





            # Telegram faylni o'chiramiz (agar hali turgan bo'lsa)


            if os.path.exists(dirty_file): os.remove(dirty_file)





            # Bazaga yozish


            await database.add_track_to_db(track_id, final_artist, final_title)





            caption_text = (f"🎵 <b>{final_artist} - {final_title}</b>\n\n"


                            f"🔥 <a href='{config.MAIN_CHANNEL_LINK}'>{config.MAIN_CHANNEL_NAME}</a>")





            reply_msg_id = None


            try:


                demo_path = final_file_path.replace(".mp3", "_demo.ogg")


                audio = AudioSegment.from_file(final_file_path)


                


                if len(audio) > 60 * 1000:


                    start_ms = 40 * 1000


                    cut_duration = demo_duration_setting * 1000


                    demo_audio = audio[start_ms : start_ms + cut_duration]


                    demo_audio.export(demo_path, format="ogg")


                    


                    demo_msg = await bot.send_voice(


                        config.MAIN_CHANNEL_ID, 


                        voice=FSInputFile(demo_path), 


                        caption=f"🎧 Parcha: {final_artist} - {final_title}"


                    )


                    reply_msg_id = demo_msg.message_id


                    os.remove(demo_path)


            except Exception as e: 


                logger.error(f"Demo xato: {e}")





            await bot.send_audio(


                config.MAIN_CHANNEL_ID,


                audio=FSInputFile(final_file_path, filename=f"{final_artist} - {final_title}.mp3"),


                caption=caption_text,


                performer=final_artist, title=final_title,


                thumbnail=FSInputFile("thumbnail.jpg") if os.path.exists("thumbnail.jpg") else None,


                reply_to_message_id=reply_msg_id


            )


            await log_to_channel(f"✅ Joylandi: {final_artist} - {final_title}")





        except Exception as e:


            logger.error(f"Post xatolik: {e}")


            await log_to_channel(f"❌ Xatolik: {e}")


        finally:


            if final_file_path and os.path.exists(final_file_path): 


                try: os.remove(final_file_path)


                except: pass


            if temp_dirty_path and os.path.exists(temp_dirty_path):


                try: os.remove(temp_dirty_path)


                except: pass

async def plan_daily_posts():
    global daily_plan
    daily_plan.clear()
    
    # Bazadan sozlamalarni o'qish
    target_count = int(database.get_setting("daily_post_count", "5"))
    
    await log_to_channel(f"🗓️ Rejalashtirish boshlandi... (Maqsad: {target_count} ta)")
    
    # --- 1-BOSQICH: 24 Soatlik qidiruv ---
    raw_tracks_24h = await userbot.get_new_music_from_channels(hours=24)
    unique_candidates = []
    seen_track_ids = set()

    for track in raw_tracks_24h:
        if track['track_id'] not in seen_track_ids:
            # Bazada borligini tekshirish
            if not await database.is_track_posted(track['track_id']):
                unique_candidates.append(track)
                seen_track_ids.add(track['track_id'])
    
    logger.info(f"24 soat ichida {len(unique_candidates)} ta yangi unikal musiqa topildi.")

    # --- 2-BOSQICH: Agar yetarli bo'lmasa, 48 soatlik qidiruv (Fallback) ---
    if len(unique_candidates) < target_count:
        await log_to_channel(f"⚠️ 24 soatlik musiqalar kam ({len(unique_candidates)} ta). 48 soatlik tarix tekshirilmoqda...")
        
        raw_tracks_48h = await userbot.get_new_music_from_channels(hours=48)
        
        for track in raw_tracks_48h:
            if track['track_id'] not in seen_track_ids:
                if not await database.is_track_posted(track['track_id']):
                    unique_candidates.append(track)
                    seen_track_ids.add(track['track_id'])
        
        logger.info(f"48 soatlik qidiruvdan keyin jami: {len(unique_candidates)} ta")

    if unique_candidates:
        # --- 3-BOSQICH: Saralash (Eng ko'p ko'rilganlar) ---
        # views bo'yicha kamayish tartibida
        unique_candidates.sort(key=lambda x: x.get('views', 0), reverse=True)
        
        # Eng zo'rlarini tanlab olish
        to_post = unique_candidates[:target_count]
        
        # Vaqtlarni hisoblash (Hozirgi vaqt + 10 daqiqadan boshlab)
        tashkent_tz = pytz.timezone("Asia/Tashkent")
        now = datetime.now(tashkent_tz)
        current_post_time = now + timedelta(minutes=10)
        
        # Tun rejimi sozlamalari
        night_mode = database.get_setting("night_mode") == "true"
        night_start = int(database.get_setting("night_start", "23"))
        night_end = int(database.get_setting("night_end", "7"))
        
        times = []
        interval_hours = 3 # Standart interval
        
        for _ in range(len(to_post)):
            # Tun rejimini tekshirish
            if night_mode:
                # Agar tun oralig'iga tushsa, vaqtni to'g'irlash
                # Mantiq: Agar soat >= start YOKI soat < end (masalan 23:00 dan 07:00 gacha)
                h = current_post_time.hour
                is_night = False
                
                if night_start > night_end: # Masalan 23 -> 7 (tundan tongga o'tish)
                    if h >= night_start or h < night_end:
                        is_night = True
                else: # Masalan 00 -> 6 (bir kun ichida)
                    if night_start <= h < night_end:
                        is_night = True
                
                if is_night:
                    # Ertalabgacha surish
                    # Agar hozir 23:30 bo'lsa va night_end=7 bo'lsa -> ertaga 07:00
                    # Agar hozir 02:00 bo'lsa va night_end=7 bo'lsa -> bugun 07:00
                    
                    target_date = current_post_time.date()
                    if h >= night_start: # Kechqurun (23:00) -> Ertaga o'tish kerak
                         target_date += timedelta(days=1)
                    
                    # Yangi vaqt: target_date soat 07:00 + kichik random (bitta vaqtda tushmasligi uchun)
                    new_time = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=night_end, minutes=random.randint(0, 30))
                    current_post_time = list(tashkent_tz.localize(new_time).timetuple())[:6] # Pytz fix
                    current_post_time = tashkent_tz.localize(datetime(*current_post_time))

            times.append(current_post_time)
            
            # Keyingi post uchun vaqt qo'shish
            current_post_time += timedelta(hours=interval_hours)
        
        for i, track in enumerate(to_post):
            run_time = times[i]
            scheduler.add_job(post_music, 'date', run_date=run_time, args=[track])
            
            # Reja ro'yxatiga qo'shish
            track_title = f"{track.get('artist')} - {track.get('title')}"
            views_count = track.get('views', 0)
            daily_plan.append({
                'title': f"{track_title} (👁 {views_count})", 
                'time': run_time.strftime('%H:%M')
            })
            
        await log_to_channel(f"✅ {len(to_post)} ta eng ommabop musiqa rejalashtirildi.")
    else:
        await log_to_channel("❌ So'nggi 48 soat ichida yangi musiqa topilmadi.")

async def check_schedule_update():
    """
    Har 15 daqiqada rejalashtirish vaqti o'zgarganini tekshiradi
    """
    try:
        current_job = scheduler.get_job('daily_planning')
        db_hour = int(database.get_setting("planning_hour", "5"))
        
        if current_job:
            # Triggerdagi vaqtni tekshirish murakkab bo'lishi mumkin, shuning uchun
            # shunchaki qayta yangilaymiz agar farq bo'lsa.
            # Lekin oddiylik uchun har doim yangilash ham mumkin.
            scheduler.reschedule_job(
                'daily_planning',
                trigger='cron',
                hour=db_hour,
                minute=0
            )
            # logger.info(f"Rejalashtirish vaqti yangilandi: {db_hour}:00")
            
    except Exception as e:
        logger.error(f"Scheduler yangilashda xato: {e}")

# --- YANGI START BUYRUG'I ---
@dp.message(Command("start", "holat"))
async def start_command(message: types.Message):
    if message.from_user.id != config.ADMIN_USER_ID:
        return

    settings = database.get_all_settings()
    text = "🤖 <b>Bot Ishlamoqda!</b>\n\n"
    text += f"⏰ Reja vaqti: <b>{settings.get('planning_hour', '?')}:00</b>\n"
    text += f"🎵 Kunlik limit: <b>{settings.get('daily_post_count', '?')} ta</b>\n"
    text += f"🔗 Web Panel: http://127.0.0.1:8000 (Local)\n\n"
    
    if daily_plan:
        text += "📋 <b>Bugungi Reja:</b>\n" + "\n".join([f"🕒 {item['time']} - {item['title']}" for item in daily_plan])
    else:
        text += "📭 Bugungi reja hali tuzilmagan yoki tugagan."
    
    await message.answer(text)

@dp.message(Command("kanaldan"))
async def force_post_from_channel(message: types.Message):
    if message.from_user.id != config.ADMIN_USER_ID: return
    await message.answer("🔍 Musiqa qidirilmoqda (Manual)...")
    tracks = await userbot.get_new_music_from_channels()
    if tracks:
        # Tasodifiy bittasini olish
        track = random.choice(tracks)
        await message.answer(f"✅ Topildi: {track['artist']} - {track['title']}\nYuklanmoqda...")
        # To'g'ridan-to'g'ri chaqiramiz (Rejaga kirmaydi)
        await post_music(track)
    else:
        await message.answer("❌ Yangi musiqa topilmadi.")

# ... Boshqa buyruqlar o'z o'rnida qoladi ...
# (Qisqartirish uchun ularni qayta yozmadim, chunki ular o'zgarmaydi)

async def set_main_menu(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="/start", description="🚀 Holat va Sozlamalar"),
        BotCommand(command="/kanaldan", description="📢 Bitta post (Manual)"),
        BotCommand(command="/rejalash", description="🔄 Majburiy rejalash")
    ])

def start_web_app():
    webapp.run_web_app()

async def on_startup(bot: Bot):
    await database.setup_database()
    
    # Userbotni ishga tushirish
    userbot_success = await userbot.start()
    if not userbot_success:
        logger.warning("Userbot ishlamadi!")
        
    await setup_scheduler()
    await set_main_menu(bot)
    
    # Web App'ni alohida thread'da ishga tushirish
    threading.Thread(target=start_web_app, daemon=True).start()
    logger.success("Web App fon rejimida ishga tushdi (Port 8000)")

async def setup_scheduler():
    scheduler.configure(timezone="Asia/Tashkent")
    
    # Bazadan vaqtni olish
    plan_hour = int(database.get_setting("planning_hour", "5"))
    
    scheduler.add_job(
        plan_daily_posts, 
        'cron', 
        hour=plan_hour, 
        minute=0,
        id='daily_planning'
    )
    
    # Sozlamalarni tekshirish uchun har 10 daqiqada job
    scheduler.add_job(
        check_schedule_update,
        'interval',
        minutes=10,
        id='settings_checker'
    )
    
    if not scheduler.running:
        scheduler.start()
    
    # Dastlabki tekshiruv: Agar hozir soat reja vaqtidan o'tgan bo'lsa va reja yo'q bo'lsa
    # (Bu qismni ehtiyotkorlik bilan qilish kerak, har safar restartda qayta reja tuzmasligi uchun)
    # Hozircha o'chirib turamiz, admin o'zi /rejalash bosishi mumkin kerak bo'lsa.

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot o'chirildi.")
