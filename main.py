import asyncio
# Python 3.12+ compatibility fix for Pyrogram get_event_loop RuntimeError
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import os
import re
import random
from typing import Dict, List
from datetime import datetime, timedelta

import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
PLANNING_LOCK = asyncio.Lock()
LAST_SETTINGS: Dict[str, str] = {}


class AdminStates(StatesGroup):
    waiting_for_search_bot = State()
    waiting_for_source_channels = State()
    waiting_for_audio_metadata = State()


def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_USER_ID


def get_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Hozir post qilish", callback_data="admin_post_now"),
            InlineKeyboardButton(text="🔄 Rejani yangilash", callback_data="admin_replan")
        ],
        [
            InlineKeyboardButton(text="📋 Rejalangan musiqalar", callback_data="admin_view_plan")
        ],
        [
            InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="admin_settings"),
            InlineKeyboardButton(text="❌ Yopish", callback_data="admin_close")
        ]
    ])
    return keyboard


def get_settings_keyboard(daily_post_count: str, planning_hour: str, demo_duration: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🎵 Limit: {daily_post_count} ta", callback_data="none"),
            InlineKeyboardButton(text="➖", callback_data="admin_count_dn"),
            InlineKeyboardButton(text="➕", callback_data="admin_count_up")
        ],
        [
            InlineKeyboardButton(text=f"⏰ Soat: {planning_hour}:00", callback_data="none"),
            InlineKeyboardButton(text="➖", callback_data="admin_hour_dn"),
            InlineKeyboardButton(text="➕", callback_data="admin_hour_up")
        ],
        [
            InlineKeyboardButton(text=f"⏳ Demo: {demo_duration}s", callback_data="none"),
            InlineKeyboardButton(text="➖", callback_data="admin_demo_dn"),
            InlineKeyboardButton(text="➕", callback_data="admin_demo_up")
        ],
        [
            InlineKeyboardButton(text="✏️ Qidiruv botini o'zgartirish", callback_data="admin_edit_search_bot")
        ],
        [
            InlineKeyboardButton(text="✏️ Manbalarni o'zgartirish", callback_data="admin_edit_sources")
        ],
        [
            InlineKeyboardButton(text="↩️ Orqaga", callback_data="admin_main")
        ]
    ])
    return keyboard


async def get_admin_panel_text() -> str:
    settings = await database.get_all_settings()
    total_tracks = len(database.posted_track_ids)
    
    text = "🤖 <b>MusiqaBot Admin Paneli</b>\n\n"
    text += f"📊 <b>Statistika:</b>\n"
    text += f"├ Bazadagi musiqalar: <b>{total_tracks} ta</b>\n"
    text += f"├ Qidiruv boti: <b>{settings.get('target_search_bot', '@Zoryuklabot')}</b>\n"
    text += f"└ Manbalar: <code>{settings.get('source_channels', '')}</code>\n\n"
    text += f"⚙️ <b>Reja sozlamalari:</b>\n"
    text += f"├ Reja vaqti: <b>{settings.get('planning_hour', '?')}:00</b>\n"
    text += f"├ Kunlik limit: <b>{settings.get('daily_post_count', '?')} ta</b>\n"
    text += f"├ Demo davomiyligi: <b>{settings.get('demo_duration', '?')} soniya</b>\n"
    text += f"└ Web Panel: https://abboscoder.uz/music\n"
        
    return text


async def log_to_channel(text: str):
    if not config.LOG_CHANNEL_ID or config.LOG_CHANNEL_ID == 0 or config.LOG_CHANNEL_ID == "0":
        logger.info(f"[LIVE] {text}")
        return
    try:
        await bot.send_message(config.LOG_CHANNEL_ID, text)
    except Exception as e:
        logger.error(f"Log kanaliga yozishda xato (Bot ishlashda davom etadi): {e}")


async def post_music(track_info: Dict):
    track_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(track_info.get('track_id', 'unknown')))
    raw_artist = track_info.get('artist') or "Unknown Artist"
    raw_title = track_info.get('title') or "Unknown Track"
    source_channel = track_info.get('source_channel') or "Noma'lum"

    # Intercept direct override files from admin schedule replacement
    direct_file = track_info.get('direct_file_path')
    if direct_file and os.path.exists(direct_file):
        try:
            final_artist = utils._clean_single_string(raw_artist) or "Trend MUSIC"
            final_title = utils._clean_single_string(raw_title) or "Musiqa"
            
            # Rewrite metadata tags in the file itself
            utils.write_clean_metadata(direct_file, final_artist, final_title)
            
            # Add to database to prevent duplicates later
            await database.add_track_to_db(track_id, final_artist, final_title)
            
            target_bot = await database.get_setting("target_search_bot", "@Zoryuklabot")
            if not target_bot.startswith("@"):
                target_bot = "@" + target_bot
                
            caption_text = (f"👇 <b>Musiqa topuvchi bot</b>\n"
                            f"{target_bot} 🔎\n\n"
                            f"👉 <a href='{config.MAIN_CHANNEL_LINK}'>Kanalga obuna bo'ling</a>")
                            
            reply_msg_id = None
            full_audio_duration = None
            demo_duration_setting = int(await database.get_setting("demo_duration", "30"))
            
            try:
                demo_path = direct_file.replace(".mp3", "_demo.ogg")
                audio = AudioSegment.from_file(direct_file)
                full_audio_duration = len(audio) // 1000
                
                if len(audio) > 60 * 1000:
                    start_ms = 40 * 1000
                    cut_duration = demo_duration_setting * 1000
                    demo_audio = audio[start_ms : start_ms + cut_duration]
                    demo_audio.export(demo_path, format="ogg", codec="libopus")
                    
                    demo_msg = await bot.send_voice(
                        config.MAIN_CHANNEL_ID,
                        voice=FSInputFile(demo_path),
                        caption="🎶 To'liq Mp3 Pastda ⬇️",
                        duration=len(demo_audio) // 1000
                    )
                    reply_msg_id = demo_msg.message_id
                    os.remove(demo_path)
            except Exception as e:
                logger.error(f"Scheduled direct override demo cutting error: {e}")
                
            await bot.send_audio(
                config.MAIN_CHANNEL_ID,
                audio=FSInputFile(direct_file, filename=f"{final_artist} - {final_title}.mp3"),
                caption=caption_text,
                performer=final_artist,
                title=final_title,
                thumbnail=FSInputFile("thumbnail.jpg") if os.path.exists("thumbnail.jpg") else None,
                reply_to_message_id=reply_msg_id,
                duration=full_audio_duration
            )
            
            await database.mark_schedule_posted(track_id)
            await log_to_channel(f"✅ Joylandi (Jadval o'rniga): {final_artist} - {final_title}")
        except Exception as e:
            logger.error(f"Error posting scheduled override file: {e}")
        finally:
            if os.path.exists(direct_file):
                try: os.remove(direct_file)
                except: pass
        return

    if await database.is_track_posted(track_id):
        logger.info(f"Trek {track_id} allaqachon joylangan.")
        return

    if await database.is_similar_track_posted(raw_artist, raw_title):
        logger.info(f"O'xshash trek allaqachon joylangan: {raw_artist} - {raw_title}")
        return

    async with PROCESSING_LOCK:
        os.makedirs("downloads", exist_ok=True)
        base_filename = f"track_{track_id}_{random.randint(1000, 9999)}"
        temp_dirty_path = os.path.join("downloads", f"{base_filename}_dirty.mp3")
        final_file_path = None
        final_artist = raw_artist
        final_title = raw_title
        demo_duration_setting = int(await database.get_setting("demo_duration", "30"))

        try:
            logger.info(f"Yangi trek qayta ishlanmoqda: {raw_artist} - {raw_title} (Manba: {source_channel})")
            
            # 1. Avval nomini tozalab, matnli qidiruv yordamida original toza variantini olishga urinish
            ai_cleaned = await utils.get_clean_details_with_ai(raw_artist, raw_title)
            
            # Xavfsizlik filtri: Diniy va siyosiy qo'shiqlarni taqiqlash
            is_religious = ai_cleaned.get('is_religious', False)
            is_political = ai_cleaned.get('is_political', False)
            is_forbidden_local = utils.check_forbidden_keywords(raw_artist, raw_title) or utils.check_forbidden_keywords(ai_cleaned.get('artist', ''), ai_cleaned.get('title', ''))
            
            if is_religious or is_political or is_forbidden_local:
                reason = ai_cleaned.get('reason') or "Taqiqlangan kalit so'z aniqlandi"
                logger.warning(f"❌ Xavfsizlik filtri ishga tushdi: {raw_artist} - {raw_title} (Manba: {source_channel}) (Diniy: {is_religious}, Siyosiy: {is_political}, Mahalliy: {is_forbidden_local}) | Sabab: {reason}")
                await log_to_channel(f"⏭️ Joylanmadi (Xavfsizlik/Diniy-Siyosiy) (Manba: {source_channel}): {raw_artist} - {raw_title}")
                # Bazada qayta urinmasligi uchun saqlaymiz
                await database.add_track_to_db(track_id, raw_artist, raw_title)
                return
            
            clean_artist = ai_cleaned.get('artist')
            clean_title = ai_cleaned.get('title')

            if not clean_artist or not clean_title or clean_artist == "Trend MUSIC" or clean_title == "Musiqa":
                ext_art, ext_tit = utils.extract_clean_artist_and_title(raw_artist, raw_title)
                if not clean_artist or clean_artist == "Trend MUSIC":
                    clean_artist = ext_art or utils._clean_single_string(raw_artist) or "Trend MUSIC"
                if not clean_title or clean_title == "Musiqa":
                    clean_title = ext_tit or utils._clean_single_string(raw_title) or "Musiqa"

            text_query = f"{clean_artist} - {clean_title}".strip()
            if clean_artist == "Trend MUSIC":
                text_query = clean_title
            
            logger.info(f"Matnli qidiruv boshlandi: '{text_query}'")
            final_file_path = await userbot.search_text_via_target_bot(text_query)
            
            if final_file_path and os.path.exists(final_file_path):
                logger.success("✅ Asosiy matnli qidiruv muvaffaqiyatli: Maqsadli botdan toza original musiqa yuklab olindi.")
                final_artist = clean_artist
                final_title = clean_title
            else:
                logger.info("ℹ️ Matnli qidiruv topmadi. Telegram Global qidiruv tekshirilmoqda...")
                final_file_path = await userbot.search_global_music(clean_artist, clean_title)
                if final_file_path and os.path.exists(final_file_path):
                    logger.success("✅ Telegram Global Qidiruvdan original musiqa olindi.")
                    final_artist = clean_artist
                    final_title = clean_title
                else:
                    logger.warning("⚠️ Global qidiruv topmadi. Forward orqali original variantini olishga urinilmoqda...")
                    final_file_path = await userbot.search_via_target_bot(track_info['chat_id'], track_info['message_id'])
                    if final_file_path and os.path.exists(final_file_path):
                        logger.success("✅ Forward qidiruv muvaffaqiyatli: Maqsadli botdan original musiqa olindi.")
                        shazam_result = await utils.identify_track_with_shazam(final_file_path)
                        if shazam_result and shazam_result.get('artist') and shazam_result.get('title'):
                            final_artist = shazam_result['artist']
                            final_title = shazam_result['title']
                        else:
                            final_artist = clean_artist
                            final_title = clean_title

            # 2. Zaxira (Fallback) Rejimi — agar maqsadli botdan ham, globaldan ham topilmasa
            if not final_file_path or not os.path.exists(final_file_path):
                dirty_file = await userbot.download_music(
                    track_info['chat_id'], track_info['message_id'], temp_dirty_path
                )

                if not dirty_file:
                    raise Exception("Telegramdan faylni yuklab bo'lmadi.")

                # Shazam orqali aniqlash
                shazam_result = await utils.identify_track_with_shazam(dirty_file)
                
                if shazam_result and shazam_result.get('artist') and shazam_result.get('title'):
                    shazam_artist = shazam_result['artist']
                    shazam_title = shazam_result['title']
                    logger.success(f"✅ Shazam aniqladi: {shazam_artist} - {shazam_title}")

                    # Global qidiruv (Shazam natijasi bilan)
                    final_file_path = await userbot.search_global_music(shazam_artist, shazam_title)
                    if final_file_path:
                        final_artist = shazam_artist
                        final_title = shazam_title
                        logger.success("✅ Zaxira manba: Telegram Global Search (Shazam)")
                    else:
                        # YouTube (Shazam natijasi bilan)
                        final_file_path = await utils.get_youtube_with_api(shazam_artist, shazam_title)
                        if final_file_path:
                            final_artist = shazam_artist
                            final_title = shazam_title
                            logger.success("✅ Zaxira manba: YouTube (Shazam)")
                
                # Agar Shazam topa olmagan bo'lsa, tozalangan nom bo'yicha YouTube'dan urinish
                if not final_file_path or not os.path.exists(final_file_path):
                    final_file_path = await utils.get_youtube_with_api(clean_artist, clean_title)
                    if final_file_path and os.path.exists(final_file_path):
                        final_artist = clean_artist
                        final_title = clean_title
                        logger.success("✅ Zaxira manba: YouTube (Cleaned Name)")

                # Vaqtinchalik faylni tozalash
                if os.path.exists(dirty_file):
                    try: os.remove(dirty_file)
                    except: pass

            # Final tekshiruv
            if not final_file_path or not os.path.exists(final_file_path):
                logger.error("❌ Barcha qidiruv usullari samarasiz bo'ldi. Post bekor qilindi.")
                await log_to_channel(f"⏭️ Joylanmadi (Topilmadi): {raw_artist} - {raw_title}")
                return

            # Clean final performer and title using the robust cleaner
            final_artist = utils._clean_single_string(final_artist) or clean_artist or "Trend MUSIC"
            final_title = utils._clean_single_string(final_title) or clean_title or "Musiqa"

            # Rewrite ID3 tags in the MP3 file itself
            utils.write_clean_metadata(final_file_path, final_artist, final_title)

            # O'xshashlikni tekshirish (final artist va nom bo'yicha)
            if await database.is_similar_track_posted(final_artist, final_title):
                logger.warning(f"O'xshash musiqa joylanganligi aniqlandi (Final): {final_artist} - {final_title}. Bekor qilinmoqda.")
                await log_to_channel(f"⏭️ Joylanmadi (O'xshash): {final_artist} - {final_title}")
                if final_file_path and os.path.exists(final_file_path):
                    os.remove(final_file_path)
                return

            # Bazaga yozish
            await database.add_track_to_db(track_id, final_artist, final_title)

            # Target bot ma'lumotlarini olish (post captionda ko'rsatish uchun)
            target_bot = await database.get_setting("target_search_bot", "@Zoryuklabot")
            if not target_bot.startswith("@"):
                target_bot = "@" + target_bot

            caption_text = (f"👇 <b>Musiqa topuvchi bot</b>\n"
                            f"{target_bot} 🔎\n\n"
                            f"👉 <a href='{config.MAIN_CHANNEL_LINK}'>Kanalga obuna bo'ling</a>")

            reply_msg_id = None
            full_audio_duration = None
            try:
                if final_file_path and os.path.exists(final_file_path):
                    demo_path = final_file_path.replace(".mp3", "_demo.ogg")
                    audio = AudioSegment.from_file(final_file_path)
                    full_audio_duration = len(audio) // 1000

                    if len(audio) > 60 * 1000:
                        start_ms = 40 * 1000
                        cut_duration = demo_duration_setting * 1000
                        demo_audio = audio[start_ms : start_ms + cut_duration]
                        demo_audio.export(demo_path, format="ogg", codec="libopus")

                        demo_msg = await bot.send_voice(
                            config.MAIN_CHANNEL_ID,
                            voice=FSInputFile(demo_path),
                            caption="🎶 To'liq Mp3 Pastda ⬇️",
                            duration=len(demo_audio) // 1000
                        )
                        reply_msg_id = demo_msg.message_id
                        os.remove(demo_path)
            except Exception as e:
                logger.error(f"Demo kesishda xato: {e}")

            await bot.send_audio(
                config.MAIN_CHANNEL_ID,
                audio=FSInputFile(final_file_path, filename=f"{final_artist} - {final_title}.mp3"),
                caption=caption_text,
                performer=final_artist, title=final_title,
                thumbnail=FSInputFile("thumbnail.jpg") if os.path.exists("thumbnail.jpg") else None,
                reply_to_message_id=reply_msg_id,
                duration=full_audio_duration
            )
            await database.mark_schedule_posted(track_id)
            await log_to_channel(f"✅ Joylandi (Manba: {source_channel}): {final_artist} - {final_title}")

        except Exception as e:
            logger.error(f"Post xatolik: {e}")
            await log_to_channel(f"❌ Xatolik: {e}")
        finally:
            if final_file_path and os.path.exists(final_file_path):
                try:
                    os.remove(final_file_path)
                except:
                    pass
            if os.path.exists(temp_dirty_path):
                try:
                    os.remove(temp_dirty_path)
                except:
                    pass


async def plan_daily_posts(force: bool = False):
    async with PLANNING_LOCK:
        await _plan_daily_posts_internal(force)


async def _plan_daily_posts_internal(force: bool = False):
    global daily_plan
    daily_plan.clear()

    # Bazadan sozlamalarni o'qish
    target_count = int(await database.get_setting("daily_post_count", "5"))

    if force:
        # Clear existing scheduled music jobs
        for job in scheduler.get_jobs():
            if job.id not in ['daily_planning', 'settings_checker']:
                job.remove()
        # Clear database schedule
        await database.clear_active_schedule()

    # 1. Avval ma'lumotlar bazasidan faol rejalarni yuklashga urinib ko'ramiz
    if not force:
        active_db_schedule = await database.get_active_schedule()
        if active_db_schedule:
            logger.info(f"🔄 Bazasdan faol {len(active_db_schedule)} ta rejalashtirilgan ishlar yuklanmoqda...")
        
            # Clear existing scheduled music jobs
            for job in scheduler.get_jobs():
                if job.id not in ['daily_planning', 'settings_checker']:
                    job.remove()
                    
            tashkent_tz = pytz.timezone("Asia/Tashkent")
            for entry in active_db_schedule:
                run_time = entry['post_time']
                if run_time.tzinfo is None:
                    run_time = tashkent_tz.localize(run_time)
                else:
                    run_time = run_time.astimezone(tashkent_tz)
                    
                track_info = {
                    'track_id': entry['track_id'],
                    'artist': entry['artist'],
                    'title': entry['title'],
                    'chat_id': entry.get('chat_id'),
                    'message_id': entry.get('message_id'),
                    'direct_file_path': entry.get('direct_file_path')
                }
                
                # Add to scheduler
                scheduler.add_job(post_music, 'date', run_date=run_time, args=[track_info])
                
                track_title = f"{entry['artist']} - {entry['title']}"
                if entry.get('direct_file_path'):
                    track_title += " (Admin)"
                
                daily_plan.append({
                    'title': track_title,
                    'time': run_time.strftime('%H:%M')
                })
                
            await log_to_channel(f"🔄 Tizim qayta ishga tushdi: Bazasdan {len(active_db_schedule)} ta rejalashtirilgan musiqa qayta yuklandi.")
            return

    await log_to_channel(f"🗓️ Rejalashtirish boshlandi... (Maqsad: {target_count} ta)")

    # --- 1-BOSQICH: So'nggi 7 kunlik musiqalarni yuklash va Toshkent vaqti bo'yicha saralash ---
    raw_tracks = await userbot.get_new_music_from_channels(hours=168)
    
    tashkent_tz = pytz.timezone("Asia/Tashkent")
    now = datetime.now(tashkent_tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    yesterday_candidates = []
    older_candidates = []
    seen_track_ids = set()

    def filter_and_categorize(tracks):
        for track in tracks:
            if track['track_id'] in seen_track_ids:
                continue
            if utils.check_forbidden_keywords(
                track.get('artist', ''), track.get('title', '')
            ):
                continue
            
            # UTC vaqtni Toshkent vaqtiga o'girish
            track_date_utc = track['date'].replace(tzinfo=pytz.utc) if track['date'].tzinfo is None else track['date'].astimezone(pytz.utc)
            track_date_uz = track_date_utc.astimezone(tashkent_tz)
            
            if track_date_uz >= today_start:
                # Bugungi musiqalarga tegmaymiz (ertaga olinadi)
                continue
            elif yesterday_start <= track_date_uz < today_start:
                yesterday_candidates.append(track)
            else:
                older_candidates.append(track)
                
            seen_track_ids.add(track['track_id'])

    filter_and_categorize(raw_tracks)

    async def check_not_posted(tracks):
        result = []
        for track in tracks:
            track_id = track['track_id']
            artist = track.get('artist', '')
            title = track.get('title', '')
            
            # Check posted status
            posted = await database.is_track_posted(track_id)
            similar_posted = await database.is_similar_track_posted(artist, title)
            
            # Check scheduled/history status
            scheduled = await database.is_track_scheduled_before(track_id)
            similar_scheduled = await database.is_similar_track_scheduled(artist, title)
            
            if not posted and not scheduled:
                if not similar_posted and not similar_scheduled:
                    result.append(track)
        return result

    # Birinchi navbatda faqat kechagi (roppa-rosa 1 kun orqadagi) musiqalarni tekshiramiz
    unique_candidates = await check_not_posted(yesterday_candidates)
    logger.info(f"Kechagi kun (1 kun oldin) uchun {len(unique_candidates)} ta yangi unikal musiqa topildi.")

    # Agar kechagi musiqalar yetarli bo'lmasa -> eski kunlardagilarni (fallback) qo'shamiz
    if len(unique_candidates) < target_count:
        needed = target_count - len(unique_candidates)
        logger.info(
            f"⚠️ Kechagi musiqalar yetarli emas ({len(unique_candidates)}/{target_count}). "
            f"Eski kunlar musiqalaridan {needed} ta zaxira olinmoqda..."
        )
        await log_to_channel(
            f"⚠️ Kechagi musiqalar soni yetarli emas. Qolgan {needed} ta musiqa eski kunlar zaxirasidan to'ldiriladi."
        )
        older_unique = await check_not_posted(older_candidates)
        # Eski kunlar musiqalarini reyting bo'yicha saralab eng yaxshilarini qo'shamiz
        older_unique.sort(key=utils.calculate_track_score, reverse=True)
        unique_candidates.extend(older_unique[:needed])
        logger.info(
            f"Zaxira bilan birga jami {len(unique_candidates)} ta unikal musiqa yig'ildi."
        )

    if unique_candidates:
        # Group candidates by source channel, sort each by score
        candidates_by_channel = {}
        for track in unique_candidates:
            cid = track.get('chat_id')
            if cid not in candidates_by_channel:
                candidates_by_channel[cid] = []
            candidates_by_channel[cid].append(track)

        for cid in candidates_by_channel:
            candidates_by_channel[cid].sort(
                key=utils.calculate_track_score, reverse=True
            )

        channel_ids = list(candidates_by_channel.keys())
        num_channels = len(channel_ids)

        # --- 60/40 taqsimoti (2 kanal bo'lsa 60/40, 1 kanal bo'lsa 100%) ---
        if num_channels == 1:
            quotas = [target_count]
        elif num_channels == 2:
            # Birinchi kanaldan 60%, ikkinchisidan 40% (kamida 1 ta)
            q0 = max(1, round(target_count * 0.6))
            q1 = max(1, target_count - q0)
            quotas = [q0, q1]
        else:
            # 3 va undan ko'p kanallar: teng taqsimot
            base = target_count // num_channels
            rem = target_count % num_channels
            quotas = [base + (1 if i < rem else 0) for i in range(num_channels)]

        to_post = []
        leftover = []
        for i, cid in enumerate(channel_ids):
            pool = candidates_by_channel[cid]
            quota = quotas[i] if i < len(quotas) else 0
            to_post.extend(pool[:quota])
            leftover.extend(pool[quota:])

        # Agar target_count ga yetmagan bo'lsak, qolganlardan to'ldiramiz
        if len(to_post) < target_count:
            leftover.sort(key=utils.calculate_track_score, reverse=True)
            needed = target_count - len(to_post)
            to_post.extend(leftover[:needed])

        # Final ro'yxatni score bo'yicha tartiblash
        to_post.sort(key=utils.calculate_track_score, reverse=True)
        to_post = to_post[:target_count]

        tashkent_tz = pytz.timezone("Asia/Tashkent")
        now = datetime.now(tashkent_tz)

        # Tun rejimi sozlamalari
        night_mode = (await database.get_setting("night_mode")) == "true"
        night_start = int(await database.get_setting("night_start", "23"))
        night_end = int(await database.get_setting("night_end", "7"))

        # Bugungi reja tugash vaqti (23:59 gacha)
        today_end_time = now.replace(hour=23, minute=59, second=0, microsecond=0)
        
        # Agar hozirgi vaqt bugungi night_start dan keyin bo'lsa yoki ungacha 1 soatdan kam qolgan bo'lsa
        if night_mode and (now >= today_end_time - timedelta(hours=1) or now.hour < night_end):
            if now.hour < night_end:
                # Bugun 00:00 - night_end orasida bo'lsak, bugunning o'ziga faqat night_end dan boshlab rejalaymiz
                start_date = now.date()
            else:
                # Kechki night_start dan keyin bo'lsak, ertangi kunga to'liq rejalaymiz
                start_date = now.date() + timedelta(days=1)
                
            start_time = tashkent_tz.localize(datetime.combine(start_date, datetime.min.time())) + timedelta(hours=night_end)
            end_time = tashkent_tz.localize(datetime.combine(start_date, datetime.min.time())) + timedelta(hours=23, minutes=59)
        else:
            # Bugungi kunning qolgan vaqtiga taqsimlaymiz
            start_time = now + timedelta(minutes=10)
            end_time = today_end_time

        times = []
        total_tracks = len(to_post)
        
        if total_tracks > 1:
            total_duration = (end_time - start_time).total_seconds()
            interval_seconds = total_duration / (total_tracks - 1)
            interval_seconds = max(900.0, interval_seconds)  # Kamida 15 daqiqa
            
            for i in range(total_tracks):
                post_time = start_time + timedelta(seconds=i * interval_seconds)
                if post_time > end_time:
                    post_time = end_time - timedelta(minutes=(total_tracks - 1 - i) * 15)
                times.append(post_time)
        elif total_tracks == 1:
            times.append(start_time)

        db_entries = []
        # --- PRE-DOWNLOAD: Rejalash paytida musiqa fayllarini yuklab olish ---
        await log_to_channel(
            f"⏬ {len(to_post)} ta musiqa faylli yuklanmoqda (oldindan tayyorlanmoqda)..."
        )

        async def predownload_track(track: Dict) -> str | None:
            """Rejalashtirilgan trek uchun fayl yuklab oladi va yo'lini qaytaradi."""
            raw_a = track.get('artist', '')
            raw_t = track.get('title', '')
            try:
                # AI bilan tozalash
                ai = await utils.get_clean_details_with_ai(raw_a, raw_t)
                c_artist = utils._clean_single_string(
                    ai.get('artist') or raw_a
                ) or "Trend MUSIC"
                c_title = utils._clean_single_string(
                    ai.get('title') or raw_t
                ) or "Musiqa"
                query = f"{c_artist} - {c_title}"

                # 1. Target bot orqali matnli qidiruv
                fpath = await userbot.search_text_via_target_bot(query)
                if fpath and os.path.exists(fpath):
                    logger.info(f"✅ [Pre-dl] Topildi (target bot): {query}")
                    return fpath

                # 2. Forward orqali zaxira
                fpath = await userbot.search_via_target_bot(
                    track.get('chat_id'), track.get('message_id')
                )
                if fpath and os.path.exists(fpath):
                    logger.info(f"✅ [Pre-dl] Topildi (forward): {query}")
                    return fpath

                # 3. Telegram Global Search
                fpath = await userbot.search_global_music(c_artist, c_title)
                if fpath and os.path.exists(fpath):
                    logger.info(f"✅ [Pre-dl] Topildi (global): {query}")
                    return fpath

                # 4. YouTube fallback
                fpath = await utils.get_youtube_with_api(c_artist, c_title)
                if fpath and os.path.exists(fpath):
                    logger.info(f"✅ [Pre-dl] Topildi (YouTube): {query}")
                    return fpath

                logger.warning(f"⚠️ [Pre-dl] Topilmadi: {query}")
                return None
            except Exception as e:
                logger.error(f"❌ [Pre-dl] Xato ({raw_a} - {raw_t}): {e}")
                return None

        # Har bir trek uchun yuklash (ketma-ket, API limitlarini hisobga olib)
        os.makedirs("downloads/scheduled", exist_ok=True)
        for track in to_post:
            fpath = await predownload_track(track)
            if fpath:
                # Move to downloads/scheduled to avoid startup deletions
                scheduled_path = os.path.join("downloads/scheduled", os.path.basename(fpath))
                try:
                    os.rename(fpath, scheduled_path)
                    fpath = scheduled_path
                except Exception as rename_err:
                    logger.error(f"Failed to move pre-downloaded file to scheduled directory: {rename_err}")
                
                track['direct_file_path'] = fpath
                # AI bilan yana bir bor tozalab, faylning Artist/Title ni yangilab qo'yamiz
                ai = await utils.get_clean_details_with_ai(
                    track.get('artist', ''), track.get('title', '')
                )
                c_a = utils._clean_single_string(ai.get('artist') or track.get('artist', '')) or "Trend MUSIC"
                c_t = utils._clean_single_string(ai.get('title') or track.get('title', '')) or "Musiqa"
                track['artist'] = c_a
                track['title'] = c_t
                utils.write_clean_metadata(fpath, c_a, c_t)

        pre_ok = sum(1 for t in to_post if t.get('direct_file_path'))
        await log_to_channel(
            f"📦 Oldindan yuklash tugadi: {pre_ok}/{len(to_post)} ta musiqa tayyor."
        )
        # -----------------------------------------------------------------------

        for i, track in enumerate(to_post):
            run_time = times[i]
            scheduler.add_job(post_music, 'date', run_date=run_time, args=[track])

            track_title = f"{track.get('artist')} - {track.get('title')}"
            views_count = track.get('views', 0)
            reactions_count = track.get('reactions', 0)
            score = round(utils.calculate_track_score(track), 1)
            daily_plan.append({
                'title': f"{track_title} (👁 {views_count}, ❤️ {reactions_count}, 📊 {score})",
                'time': run_time.strftime('%H:%M')
            })

            db_entries.append({
                'post_time': run_time,
                'track_id': track['track_id'],
                'artist': track.get('artist'),
                'title': track.get('title'),
                'chat_id': track.get('chat_id'),
                'message_id': track.get('message_id'),
                'direct_file_path': track.get('direct_file_path'),
                'is_posted': False
            })

        await database.save_daily_schedule(db_entries)
        await log_to_channel(f"✅ {len(to_post)} ta eng ommabop musiqa rejalashtirildi.")
    else:
        await log_to_channel("❌ So'nggi 168 soat ichida yangi musiqa topilmadi.")


async def trigger_manual_post_from_action():
    try:
        logger.info("⚡ Admin panelidan tezkor joylash buyrug'i bajarilmoqda...")
        tracks = await userbot.get_new_music_from_channels(hours=168)
        available_tracks = []
        for track in tracks:
            if not await database.is_track_posted(track['track_id']):
                if not await database.is_similar_track_posted(track.get('artist', ''), track.get('title', '')):
                    available_tracks.append(track)

        if available_tracks:
            available_tracks.sort(key=utils.calculate_track_score, reverse=True)
            top_candidates = available_tracks[:15]
            track = random.choice(top_candidates)
            score = round(utils.calculate_track_score(track), 1)
            await log_to_channel(f"⚡ Tezkor joylash (Ball: {score}): {track['artist']} - {track['title']}")
            await post_music(track)
        else:
            await log_to_channel("❌ Joylanmagan yangi musiqa topilmadi.")
    except Exception as e:
        logger.error(f"Tezkor joylashda xatolik: {e}")


async def check_schedule_update():
    global LAST_SETTINGS
    try:
        settings = await database.get_all_settings()
        
        # 1. Tezkor buyruqlarni tekshirish (action_trigger)
        action = settings.get("action_trigger", "idle")
        if action != "idle":
            logger.info(f"⚡ Admin panelidan buyruq olindi: {action}")
            await database.set_setting("action_trigger", "idle")
            if action == "post_now":
                asyncio.create_task(trigger_manual_post_from_action())
            elif action == "replan":
                asyncio.create_task(plan_daily_posts(force=True))
        
        # 2. Sozlamalar o'zgarganligini tekshirish
        changed = False
        keys_to_check = ["planning_hour", "daily_post_count", "night_mode", "night_start", "night_end", "source_channels", "target_search_bot"]
        for key in keys_to_check:
            if settings.get(key) != LAST_SETTINGS.get(key):
                changed = True
                break

        if changed:
            logger.info("⚙️ Sozlamalar o'zgardi. Jadval yangilanmoqda...")
            
            # Update source channels list in config dynamically
            if 'source_channels' in settings:
                config.SOURCE_CHANNELS = [ch.strip() for ch in re.split(r'[\s,]+', settings['source_channels']) if ch.strip()]
                # Automatically trigger userbot to join new source channels
                asyncio.create_task(userbot._join_source_channels())
            if 'target_search_bot' in settings:
                config.TARGET_SEARCH_BOT = settings['target_search_bot']
                
            LAST_SETTINGS = settings
            
            # Reschedule daily planning cron job
            db_hour = int(settings.get("planning_hour", "5"))
            scheduler.reschedule_job(
                'daily_planning',
                trigger='cron',
                hour=db_hour,
                minute=0
            )
            
            # Clear all current post_music jobs
            for job in scheduler.get_jobs():
                if job.id not in ['daily_planning', 'settings_checker']:
                    job.remove()
            
            # Instantly replan with the new settings
            await plan_daily_posts(force=True)
            
    except Exception as e:
        logger.error(f"Scheduler yangilashda xato: {e}")


# --- Telegram Bot Handlerlari ---

@dp.message(Command("start", "holat"))
async def start_command(message: types.Message):
    if not is_admin(message.from_user.id):
        # Oddiy foydalanuvchilar uchun start
        await message.answer("👋 <b>Musiqa topuvchi botga xush kelibsiz!</b>\n\nMusiqa topish uchun uning <b>nomini</b> yozing yoki menga <b>ovozli xabar (voice)</b> yuboring. 🔎")
        return

    text = await get_admin_panel_text()
    await message.answer(text, reply_markup=get_admin_keyboard())


@dp.message(Command("admin"))
async def admin_menu_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    text = await get_admin_panel_text()
    await message.answer(text, reply_markup=get_admin_keyboard())


@dp.callback_query(lambda c: c.data and c.data.startswith("admin_"))
async def admin_callback_handler(query: CallbackQuery, state: FSMContext):
    if not is_admin(query.from_user.id):
        await query.answer("Siz admin emassiz!", show_alert=True)
        return

    # FSM active state cleanup if clicking another inline button
    current_state = await state.get_state()
    if current_state is not None:
        state_data = await state.get_data()
        prompt_msg_id = state_data.get("prompt_msg_id")
        if prompt_msg_id:
            try:
                await bot.delete_message(chat_id=query.message.chat.id, message_id=prompt_msg_id)
            except Exception:
                pass
        await state.clear()

    data = query.data
    
    if data == "admin_close":
        await query.message.delete()
        await query.answer()
        return
        
    elif data == "admin_main":
        text = await get_admin_panel_text()
        await query.message.edit_text(text, reply_markup=get_admin_keyboard())
        await query.answer()
        
    elif data == "admin_settings":
        settings = await database.get_all_settings()
        text = (
            "⚙️ <b>Bot Sozlamalari</b>\n\n"
            f"🎵 Kunlik postlar soni: <b>{settings.get('daily_post_count', '?')} ta</b>\n"
            f"⏰ Rejalashtirish soati: <b>{settings.get('planning_hour', '?')}:00</b>\n"
            f"⏳ Demo davomiyligi: <b>{settings.get('demo_duration', '?')} soniya</b>\n"
            f"🤖 Qidiruv boti: <b>{settings.get('target_search_bot', '?')}</b>\n"
            f"📡 Manbalar: <code>{settings.get('source_channels', '')}</code>"
        )
        await query.message.edit_text(
            text, 
            reply_markup=get_settings_keyboard(
                settings.get('daily_post_count', '5'),
                settings.get('planning_hour', '5'),
                settings.get('demo_duration', '30')
            )
        )
        await query.answer()
        
    elif data == "admin_post_now":
        await query.answer("⚡ Tezkor joylash boshlandi. Kanalni tekshiring!", show_alert=True)
        asyncio.create_task(trigger_manual_post_from_action())
        await asyncio.sleep(1)
        text = await get_admin_panel_text()
        try:
            await query.message.edit_text(text, reply_markup=get_admin_keyboard())
        except Exception:
            pass
            
    elif data == "admin_replan":
        try:
            await query.message.edit_text("🔄 <b>Bugungi kunlik reja qayta tuzilmoqda...</b>\n\nIltimos, kuting (taxminan 3-5 soniya)...")
        except Exception:
            pass
        await query.answer()
        await plan_daily_posts(force=True)
        text = await get_admin_panel_text()
        try:
            await query.message.edit_text(text, reply_markup=get_admin_keyboard())
        except Exception:
            pass

            
    elif data == "admin_view_plan":
        text = "📋 <b>Bugungi rejalashtirilgan musiqalar:</b>\n\n"
        if daily_plan:
            text += "\n".join([f"🕒 <b>{item['time']}</b> — {item['title']}" for item in daily_plan])
        else:
            text += "📭 Bugungi reja hali tuzilmagan yoki tugagan."
            
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Orqaga", callback_data="admin_main")]
        ])
        await query.message.edit_text(text, reply_markup=keyboard)
        await query.answer()

    elif data in ["admin_count_up", "admin_count_dn"]:
        settings = await database.get_all_settings()
        curr = int(settings.get('daily_post_count', '5'))
        new_val = curr + 1 if "up" in data else max(1, curr - 1)
        await database.set_setting('daily_post_count', str(new_val))
        await query.answer(f"Kunlik limit: {new_val}")
        settings = await database.get_all_settings()
        text = (
            "⚙️ <b>Bot Sozlamalari</b>\n\n"
            f"🎵 Kunlik postlar soni: <b>{settings.get('daily_post_count', '?')} ta</b>\n"
            f"⏰ Rejalashtirish soati: <b>{settings.get('planning_hour', '?')}:00</b>\n"
            f"⏳ Demo davomiyligi: <b>{settings.get('demo_duration', '?')} soniya</b>\n"
            f"🤖 Qidiruv boti: <b>{settings.get('target_search_bot', '?')}</b>\n"
            f"📡 Manbalar: <code>{settings.get('source_channels', '')}</code>"
        )
        try:
            await query.message.edit_text(
                text, 
                reply_markup=get_settings_keyboard(
                    settings.get('daily_post_count', '5'),
                    settings.get('planning_hour', '5'),
                    settings.get('demo_duration', '30')
                )
            )
        except Exception:
            pass
            
    elif data in ["admin_hour_up", "admin_hour_dn"]:
        settings = await database.get_all_settings()
        curr = int(settings.get('planning_hour', '5'))
        new_val = (curr + 1) % 24 if "up" in data else (curr - 1) % 24
        await database.set_setting('planning_hour', str(new_val))
        await query.answer(f"Rejalash soati: {new_val}:00")
        settings = await database.get_all_settings()
        text = (
            "⚙️ <b>Bot Sozlamalari</b>\n\n"
            f"🎵 Kunlik postlar soni: <b>{settings.get('daily_post_count', '?')} ta</b>\n"
            f"⏰ Rejalashtirish soati: <b>{settings.get('planning_hour', '?')}:00</b>\n"
            f"⏳ Demo davomiyligi: <b>{settings.get('demo_duration', '?')} soniya</b>\n"
            f"🤖 Qidiruv boti: <b>{settings.get('target_search_bot', '?')}</b>\n"
            f"📡 Manbalar: <code>{settings.get('source_channels', '')}</code>"
        )
        try:
            await query.message.edit_text(
                text, 
                reply_markup=get_settings_keyboard(
                    settings.get('daily_post_count', '5'),
                    settings.get('planning_hour', '5'),
                    settings.get('demo_duration', '30')
                )
            )
        except Exception:
            pass
            
    elif data in ["admin_demo_up", "admin_demo_dn"]:
        settings = await database.get_all_settings()
        curr = int(settings.get('demo_duration', '30'))
        new_val = curr + 5 if "up" in data else max(5, curr - 5)
        await database.set_setting('demo_duration', str(new_val))
        await query.answer(f"Demo davomiyligi: {new_val}s")
        settings = await database.get_all_settings()
        text = (
            "⚙️ <b>Bot Sozlamalari</b>\n\n"
            f"🎵 Kunlik postlar soni: <b>{settings.get('daily_post_count', '?')} ta</b>\n"
            f"⏰ Rejalashtirish soati: <b>{settings.get('planning_hour', '?')}:00</b>\n"
            f"⏳ Demo davomiyligi: <b>{settings.get('demo_duration', '?')} soniya</b>\n"
            f"🤖 Qidiruv boti: <b>{settings.get('target_search_bot', '?')}</b>\n"
            f"📡 Manbalar: <code>{settings.get('source_channels', '')}</code>"
        )
        try:
            await query.message.edit_text(
                text, 
                reply_markup=get_settings_keyboard(
                    settings.get('daily_post_count', '5'),
                    settings.get('planning_hour', '5'),
                    settings.get('demo_duration', '30')
                )
            )
        except Exception:
            pass

    elif data == "admin_edit_search_bot":
        prompt_msg = await query.message.answer("✏️ Yangi qidiruv botini kiriting (masalan: <code>@Zoryuklabot</code>):")
        await state.update_data(prompt_msg_id=prompt_msg.message_id, settings_msg_id=query.message.message_id)
        await state.set_state(AdminStates.waiting_for_search_bot)
        await query.answer()

    elif data == "admin_edit_sources":
        settings = await database.get_all_settings()
        current_sources = settings.get('source_channels', '')
        prompt_text = (
            "📡 <b>Yangi manba kanallarni kiriting:</b>\n\n"
            f"Hozirgi ro'yxat: <code>{current_sources}</code>\n\n"
            "🔹 <b>Qo'shish:</b> shunchaki yangi kanallarni yuboring (masalan: <code>@kanal3, @kanal4</code>)\n"
            "🔸 <b>O'chirish:</b> kanal nomidan oldin minus qo'ying (masalan: <code>-@kanal1</code>)\n"
            "⚠️ <b>Butunlay almashtirish:</b> boshiga undov qo'ying (masalan: <code>!@kanal1, @kanal2</code>)"
        )
        prompt_msg = await query.message.answer(prompt_text)
        await state.update_data(prompt_msg_id=prompt_msg.message_id, settings_msg_id=query.message.message_id)
        await state.set_state(AdminStates.waiting_for_source_channels)
        await query.answer()


@dp.message(AdminStates.waiting_for_search_bot)
async def process_search_bot_input(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
        
    val = message.text.strip()
    
    # Get stored prompt & settings message ids
    state_data = await state.get_data()
    prompt_msg_id = state_data.get("prompt_msg_id")
    settings_msg_id = state_data.get("settings_msg_id")
    
    # Try deleting the user's input message to keep chat clean
    try:
        await message.delete()
    except Exception:
        pass

    # Try deleting the previous prompt message
    if prompt_msg_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception:
            pass

    if not val.startswith("@") or len(val) < 3:
        # Invalid input! Send new prompt and update prompt_msg_id
        new_prompt = await message.answer("❌ Xato! Bot nomi @ belgisi bilan boshlanishi va kamida 3 belgidan iborat bo'lishi kerak. Qaytadan urinib ko'ring:")
        await state.update_data(prompt_msg_id=new_prompt.message_id)
        return
        
    await database.set_setting("target_search_bot", val)
    await state.clear()
    
    settings = await database.get_all_settings()
    text = (
        "⚙️ <b>Bot Sozlamalari</b>\n\n"
        f"🎵 Kunlik postlar soni: <b>{settings.get('daily_post_count', '?')} ta</b>\n"
        f"⏰ Rejalashtirish soati: <b>{settings.get('planning_hour', '?')}:00</b>\n"
        f"⏳ Demo davomiyligi: <b>{settings.get('demo_duration', '?')} soniya</b>\n"
        f"🤖 Qidiruv boti: <b>{settings.get('target_search_bot', '?')}</b>\n"
        f"📡 Manbalar: <code>{settings.get('source_channels', '')}</code>"
    )
    
    edited = False
    if settings_msg_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=settings_msg_id,
                text=f"✅ Qidiruv boti muvaffaqiyatli o'zgartirildi!\n\n{text}",
                reply_markup=get_settings_keyboard(
                    settings.get('daily_post_count', '5'),
                    settings.get('planning_hour', '5'),
                    settings.get('demo_duration', '30')
                )
            )
            edited = True
        except Exception:
            pass
            
    if not edited:
        await message.answer(
            f"✅ Qidiruv boti muvaffaqiyatli o'zgartirildi!\n\n{text}",
            reply_markup=get_settings_keyboard(
                settings.get('daily_post_count', '5'),
                settings.get('planning_hour', '5'),
                settings.get('demo_duration', '30')
            )
        )


@dp.message(AdminStates.waiting_for_source_channels)
async def process_source_channels_input(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
        
    val = message.text.strip()
    
    # Get stored prompt & settings message ids
    state_data = await state.get_data()
    prompt_msg_id = state_data.get("prompt_msg_id")
    settings_msg_id = state_data.get("settings_msg_id")
    
    # Try deleting the user's input message to keep chat clean
    try:
        await message.delete()
    except Exception:
        pass

    # Try deleting the previous prompt message
    if prompt_msg_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception:
            pass

    # Fetch current settings to read current channels list
    settings = await database.get_all_settings()
    current_val = settings.get('source_channels', '')
    current_channels = [ch.strip() for ch in current_val.split(",") if ch.strip()]

    if val.startswith("!"):
        # Replace mode: strip the leading "!"
        val_clean = val[1:].strip()
        channels = [ch.strip() for ch in val_clean.split(",") if ch.strip()]
        invalid = [ch for ch in channels if not ch.startswith("@")]
        if invalid:
            new_prompt = await message.answer("❌ Xato! Barcha kanallar nomi @ belgisi bilan boshlanishi kerak. Qaytadan urinib ko'ring:")
            await state.update_data(prompt_msg_id=new_prompt.message_id)
            return
        new_list = channels
    else:
        # Add / Remove mode
        inputs = [ch.strip() for ch in val.split(",") if ch.strip()]
        
        # Validate that all inputs either start with @ or -@ or +@
        invalid = []
        for ch in inputs:
            if ch.startswith("-@") or ch.startswith("+@"):
                continue
            if ch.startswith("@"):
                continue
            invalid.append(ch)
            
        if invalid:
            new_prompt = await message.answer(
                "❌ Xato! Barcha kanallar nomi @ belgisi bilan boshlanishi kerak (o'chirish uchun -@kanal).\n"
                "Qaytadan urinib ko'ring:"
            )
            await state.update_data(prompt_msg_id=new_prompt.message_id)
            return
            
        new_list = list(current_channels)
        for ch in inputs:
            if ch.startswith("-"):
                target = ch[1:]
                if target in new_list:
                    new_list.remove(target)
            elif ch.startswith("+"):
                target = ch[1:]
                if target not in new_list:
                    new_list.append(target)
            else:
                target = ch
                if target not in new_list:
                    new_list.append(target)
                    
    # Save back
    new_val = ", ".join(new_list)
    await database.set_setting("source_channels", new_val)
    await state.clear()
    
    settings = await database.get_all_settings()
    text = (
        "⚙️ <b>Bot Sozlamalari</b>\n\n"
        f"🎵 Kunlik postlar soni: <b>{settings.get('daily_post_count', '?')} ta</b>\n"
        f"⏰ Rejalashtirish soati: <b>{settings.get('planning_hour', '?')}:00</b>\n"
        f"⏳ Demo davomiyligi: <b>{settings.get('demo_duration', '?')} soniya</b>\n"
        f"🤖 Qidiruv boti: <b>{settings.get('target_search_bot', '?')}</b>\n"
        f"📡 Manbalar: <code>{settings.get('source_channels', '')}</code>"
    )
    
    edited = False
    if settings_msg_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=settings_msg_id,
                text=f"✅ Manbalar ro'yxati muvaffaqiyatli o'zgartirildi!\n\n{text}",
                reply_markup=get_settings_keyboard(
                    settings.get('daily_post_count', '5'),
                    settings.get('planning_hour', '5'),
                    settings.get('demo_duration', '30')
                )
            )
            edited = True
        except Exception:
            pass
            
    if not edited:
        await message.answer(
            f"✅ Manbalar ro'yxati muvaffaqiyatli o'zgartirildi!\n\n{text}",
            reply_markup=get_settings_keyboard(
                settings.get('daily_post_count', '5'),
                settings.get('planning_hour', '5'),
                settings.get('demo_duration', '30')
            )
        )


@dp.message(Command("kanaldan"))
async def force_post_from_channel(message: types.Message):
    logger.info(f"Incoming /kanaldan command from User ID: {message.from_user.id} | Username: @{message.from_user.username}")
    if message.from_user.id != config.ADMIN_USER_ID:
        logger.warning(f"Unauthorized /kanaldan command attempt by User ID: {message.from_user.id}")
        return
    
    await message.answer("🔍 Manba kanallardan so'nggi 7 kundagi yangi ommabop musiqalar qidirilmoqda...")
    
    # 7 kunlik yangi musiqalarni olish
    tracks = await userbot.get_new_music_from_channels(hours=168)
    
    # Faqat hali joylanmagan va o'xshash bo'lmaganlarini ajratish
    available_tracks = []
    for track in tracks:
        # Xavfsizlik filtri: diniy/siyosiy musiqalarni chetlab o'tamiz
        if utils.check_forbidden_keywords(track.get('artist', ''), track.get('title', '')):
            continue
        if not await database.is_track_posted(track['track_id']):
            if not await database.is_similar_track_posted(track.get('artist', ''), track.get('title', '')):
                available_tracks.append(track)

    if available_tracks:
        # Score bo'yicha saralash va eng yaxshi top 15 tasidan birini tanlash
        available_tracks.sort(key=utils.calculate_track_score, reverse=True)
        top_candidates = available_tracks[:15]
        track = random.choice(top_candidates)
        views_count = track.get('views', 0)
        reactions_count = track.get('reactions', 0)
        score = round(utils.calculate_track_score(track), 1)
        await message.answer(f"✅ Sifatli musiqa topildi (Ko'rilganligi: {views_count}, Reaksiyalar: {reactions_count}, Ball: {score}): <b>{track['artist']} - {track['title']}</b>\nKanalga yuklash boshlandi...")
        await post_music(track)
    else:
        await message.answer("❌ Manba kanallardan so'nggi 7 kun ichida hali joylanmagan yangi musiqa topilmadi.")


@dp.message(Command("rejalash"))
async def force_replan_command(message: types.Message):
    logger.info(f"Incoming /rejalash command from User ID: {message.from_user.id} | Username: @{message.from_user.username}")
    if message.from_user.id != config.ADMIN_USER_ID:
        logger.warning(f"Unauthorized /rejalash command attempt by User ID: {message.from_user.id}")
        return
    await message.answer("🔄 Kunlik reja majburan qayta tuzilmoqda...")
    try:
        await plan_daily_posts(force=True)
        await message.answer("✅ Kunlik reja muvaffaqiyatli qayta tuzildi!")
    except Exception as e:
        logger.error(f"Majburiy rejalashtirishda xato: {e}")
        await message.answer("❌ Xatolik yuz berdi. Tafsilotlar tizim loglarida.")


# --- Musiqa Qidirish (VKM / Shazam Bot mantiqi) ---

@dp.message(lambda msg: msg.text and not msg.text.startswith("/"))
async def text_search_handler(message: types.Message):
    raw_query = message.text.strip()
    query = utils.clean_search_query(raw_query)
    status_msg = await message.answer(f"🔍 Musiqa qidirilmoqda: <b>{query}</b>...")
    
    try:
        # 1. Target Bot (VK) orqali qidirish
        file_path = await userbot.search_text_via_target_bot(query)
        
        # 2. Agar topilmasa, Telegram Global Search orqali zaxira qidiruv
        if not file_path:
            logger.info("Target botdan topilmadi, Global Search ishlatilmoqda...")
            file_path = await userbot.search_global_music("", query)
            
        # 3. Agar hali ham topilmasa, YouTube Fallback
        if not file_path:
            logger.info("Global Searchdan topilmadi, YouTube ishlatilmoqda...")
            file_path = await utils.get_youtube_with_api("", query)
            
        if file_path and os.path.exists(file_path):
            await status_msg.delete()
            # Shazam orqali toza nomini aniqlash (Audio yuborishda muqova uchun)
            shazam_res = await utils.identify_track_with_shazam(file_path)
            performer = shazam_res['artist'] if shazam_res else ""
            title = shazam_res['title'] if shazam_res else query
            
            await message.reply_audio(
                audio=FSInputFile(file_path),
                performer=performer,
                title=title,
                caption=f"👉 @{(await bot.get_me()).username} orqali topildi!"
            )
            os.remove(file_path)
        else:
            await status_msg.edit_text("❌ Afsuski, hech qanday musiqa topilmadi. Boshqa so'zlar bilan qidirib ko'ring.")
    except Exception as e:
        logger.error(f"Matnli qidiruvda xatolik: {e}")
        await status_msg.edit_text("❌ Musiqa qidirishda kutilmagan xatolik yuz berdi.")


async def process_and_post_direct_orig(status_msg: types.Message, file_id: str, artist: str, title: str):
    temp_file_path = None
    try:
        os.makedirs("downloads", exist_ok=True)
        base_filename = f"direct_orig_{random.randint(1000, 9999)}"
        temp_file_path = os.path.join("downloads", f"{base_filename}.mp3")
        
        # Download the file from telegram
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, temp_file_path)
        
        # Clean artist/title with AI
        ai_cleaned = await utils.get_clean_details_with_ai(artist, title)
        clean_artist = utils._clean_single_string(ai_cleaned.get('artist') or artist)
        clean_title = utils._clean_single_string(ai_cleaned.get('title') or title)
        if not clean_artist: clean_artist = "Trend MUSIC"
        if not clean_title: clean_title = "Musiqa"
        
        # Clean metadata of the original file
        utils.write_clean_metadata(temp_file_path, clean_artist, clean_title)
        
        target_bot = await database.get_setting("target_search_bot", "@Zoryuklabot")
        if not target_bot.startswith("@"):
            target_bot = "@" + target_bot

        caption_text = (f"👇 <b>Musiqa topuvchi bot</b>\n"
                        f"{target_bot} 🔎\n\n"
                        f"👉 <a href='{config.MAIN_CHANNEL_LINK}'>Kanalga obuna bo'ling</a>")
        
        # Cut demo and post
        reply_msg_id = None
        full_audio_duration = None
        demo_duration_setting = int(await database.get_setting("demo_duration", "30"))
        demo_path = temp_file_path.replace(".mp3", "_demo.ogg")
        
        try:
            audio = AudioSegment.from_file(temp_file_path)
            full_audio_duration = len(audio) // 1000
            if len(audio) > 60 * 1000:
                start_ms = 40 * 1000
                cut_duration = demo_duration_setting * 1000
                demo_audio = audio[start_ms : start_ms + cut_duration]
                demo_audio.export(demo_path, format="ogg", codec="libopus")
                
                demo_msg = await bot.send_voice(
                    config.MAIN_CHANNEL_ID,
                    voice=FSInputFile(demo_path),
                    caption="🎶 To'liq Mp3 Pastda ⬇️",
                    duration=len(demo_audio) // 1000
                )
                reply_msg_id = demo_msg.message_id
                os.remove(demo_path)
        except Exception as e:
            logger.error(f"Direct orig demo cutting error: {e}")
            
        # Post full MP3
        await bot.send_audio(
            config.MAIN_CHANNEL_ID,
            audio=FSInputFile(temp_file_path, filename=f"{clean_artist} - {clean_title}.mp3"),
            caption=caption_text,
            performer=clean_artist,
            title=clean_title,
            thumbnail=FSInputFile("thumbnail.jpg") if os.path.exists("thumbnail.jpg") else None,
            reply_to_message_id=reply_msg_id,
            duration=full_audio_duration
        )
        
        await status_msg.edit_text("✅ <b>Musiqa muvaffaqiyatli qayta ishlandi va kanalga joylandi!</b>")
    except Exception as e:
        logger.error(f"process_and_post_direct_orig error: {e}")
        await status_msg.edit_text("❌ <b>Qayta ishlashda xatolik yuz berdi.</b> Tafsilotlar tizim loglarida.")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try: os.remove(temp_file_path)
            except: pass


async def process_and_post_direct_bot(status_msg: types.Message, artist: str, title: str):
    temp_file_path = None
    try:
        query = utils.clean_search_query(f"{artist} - {title}")
        file_path = await userbot.search_text_via_target_bot(query)
        if not file_path:
            file_path = await userbot.search_global_music(artist, title)
        if not file_path:
            file_path = await utils.get_youtube_with_api(artist, title)
            
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ <b>Qidiruv boti orqali original fayl topilmadi.</b>")
            return
            
        temp_file_path = file_path
        
        # Clean artist/title with AI
        ai_cleaned = await utils.get_clean_details_with_ai(artist, title)
        clean_artist = utils._clean_single_string(ai_cleaned.get('artist') or artist)
        clean_title = utils._clean_single_string(ai_cleaned.get('title') or title)
        if not clean_artist: clean_artist = "Trend MUSIC"
        if not clean_title: clean_title = "Musiqa"
        
        # Clean metadata of the original file
        utils.write_clean_metadata(temp_file_path, clean_artist, clean_title)
        
        target_bot = await database.get_setting("target_search_bot", "@Zoryuklabot")
        if not target_bot.startswith("@"):
            target_bot = "@" + target_bot

        caption_text = (f"👇 <b>Musiqa topuvchi bot</b>\n"
                        f"{target_bot} 🔎\n\n"
                        f"👉 <a href='{config.MAIN_CHANNEL_LINK}'>Kanalga obuna bo'ling</a>")
        
        # Cut demo and post
        reply_msg_id = None
        full_audio_duration = None
        demo_duration_setting = int(await database.get_setting("demo_duration", "30"))
        demo_path = temp_file_path.replace(".mp3", "_demo.ogg")
        
        try:
            audio = AudioSegment.from_file(temp_file_path)
            full_audio_duration = len(audio) // 1000
            if len(audio) > 60 * 1000:
                start_ms = 40 * 1000
                cut_duration = demo_duration_setting * 1000
                demo_audio = audio[start_ms : start_ms + cut_duration]
                demo_audio.export(demo_path, format="ogg", codec="libopus")
                
                demo_msg = await bot.send_voice(
                    config.MAIN_CHANNEL_ID,
                    voice=FSInputFile(demo_path),
                    caption="🎶 To'liq Mp3 Pastda ⬇️",
                    duration=len(demo_audio) // 1000
                )
                reply_msg_id = demo_msg.message_id
                os.remove(demo_path)
        except Exception as e:
            logger.error(f"Direct bot demo cutting error: {e}")
            
        # Post full MP3
        await bot.send_audio(
            config.MAIN_CHANNEL_ID,
            audio=FSInputFile(temp_file_path, filename=f"{clean_artist} - {clean_title}.mp3"),
            caption=caption_text,
            performer=clean_artist,
            title=clean_title,
            thumbnail=FSInputFile("thumbnail.jpg") if os.path.exists("thumbnail.jpg") else None,
            reply_to_message_id=reply_msg_id,
            duration=full_audio_duration
        )
        
        await status_msg.edit_text("✅ <b>Qidiruv boti orqali original fayl yuklab olindi va kanalga joylandi!</b>")
    except Exception as e:
        logger.error(f"process_and_post_direct_bot error: {e}")
        await status_msg.edit_text("❌ <b>Qayta ishlashda xatolik yuz berdi.</b> Tafsilotlar tizim loglarida.")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try: os.remove(temp_file_path)
            except: pass


async def process_and_schedule_direct_orig(status_msg: types.Message, file_id: str, artist: str, title: str):
    temp_file_path = None
    try:
        # Find next scheduled job
        post_jobs = []
        for job in scheduler.get_jobs():
            if job.id not in ['daily_planning', 'settings_checker']:
                post_jobs.append(job)
        if not post_jobs:
            await status_msg.edit_text("❌ <b>Jadvalda rejalashtirilgan musiqalar topilmadi.</b>")
            return
            
        post_jobs.sort(key=lambda j: j.next_run_time)
        next_job = None
        for job in post_jobs:
            track_info = job.args[0] if job.args else {}
            if 'direct_file_path' not in track_info:
                next_job = job
                break
        if not next_job:
            next_job = post_jobs[0]
        run_time = next_job.next_run_time
        time_str = run_time.strftime('%H:%M')
        
        # Download the file from telegram
        os.makedirs("downloads", exist_ok=True)
        # Create a unique track ID for DB
        track_id = f"sched_orig_{random.randint(100000, 999999)}"
        base_filename = f"sched_orig_{track_id}"
        temp_file_path = os.path.join("downloads", f"{base_filename}.mp3")
        
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, temp_file_path)
        
        # Clean artist/title with AI
        ai_cleaned = await utils.get_clean_details_with_ai(artist, title)
        clean_artist = utils._clean_single_string(ai_cleaned.get('artist') or artist) or "Trend MUSIC"
        clean_title = utils._clean_single_string(ai_cleaned.get('title') or title) or "Musiqa"
        
        # Check forbidden keywords (local or AI)
        is_religious = ai_cleaned.get('is_religious', False)
        is_political = ai_cleaned.get('is_political', False)
        is_forbidden_local = utils.check_forbidden_keywords(clean_artist, clean_title)
        if is_religious or is_political or is_forbidden_local:
            await status_msg.edit_text("❌ <b>Xavfsizlik filtri:</b> Bu qo'shiq rejalashtirish uchun ruxsat etilmagan.")
            if os.path.exists(temp_file_path):
                try: os.remove(temp_file_path)
                except: pass
            return

        # Clean metadata of the original file
        utils.write_clean_metadata(temp_file_path, clean_artist, clean_title)
        
        # Save file to a persistent path for the scheduler to use when the time comes
        persistent_file_path = os.path.join("downloads", f"sched_file_{track_id}.mp3")
        os.rename(temp_file_path, persistent_file_path)
        
        # Get old job arguments to log or replace
        old_track = next_job.args[0]
        old_title = f"{old_track.get('artist', 'Unknown')} - {old_track.get('title', 'Unknown')}"
        
        # Modify the next job
        track_info = {
            'track_id': track_id,
            'artist': clean_artist,
            'title': clean_title,
            'direct_file_path': persistent_file_path
        }
        next_job.modify(args=[track_info])
        
        # Persist to database daily_schedule
        await database.update_schedule_entry(run_time, track_id, clean_artist, clean_title, persistent_file_path)
        
        # Update daily_plan
        global daily_plan
        for entry in daily_plan:
            if entry['time'] == time_str:
                entry['title'] = f"{clean_artist} - {clean_title} (Admin)"
                break
                
        await status_msg.edit_text(
            f"✅ <b>Jadval yangilandi!</b>\n\n"
            f"🕒 Vaqti: <b>{time_str}</b>\n"
            f"⏮️ Eski musiqa: <i>{old_title}</i>\n"
            f"⏭️ Yangi musiqa: <b>{clean_artist} - {clean_title}</b>"
        )
        await log_to_channel(f"📅 Jadval yangilandi (Vaqt: {time_str}): {old_title} ➡️ {clean_artist} - {clean_title}")
    except Exception as e:
        logger.error(f"process_and_schedule_direct_orig error: {e}")
        await status_msg.edit_text("❌ <b>Qayta ishlashda xatolik yuz berdi.</b> Tafsilotlar tizim loglarida.")

async def process_and_schedule_direct_bot(status_msg: types.Message, artist: str, title: str):
    temp_file_path = None
    try:
        # Find next scheduled job
        post_jobs = []
        for job in scheduler.get_jobs():
            if job.id not in ['daily_planning', 'settings_checker']:
                post_jobs.append(job)
        if not post_jobs:
            await status_msg.edit_text("❌ <b>Jadvalda rejalashtirilgan musiqalar topilmadi.</b>")
            return
            
        post_jobs.sort(key=lambda j: j.next_run_time)
        next_job = None
        for job in post_jobs:
            track_info = job.args[0] if job.args else {}
            if 'direct_file_path' not in track_info:
                next_job = job
                break
        if not next_job:
            next_job = post_jobs[0]
        run_time = next_job.next_run_time
        time_str = run_time.strftime('%H:%M')
        
        query = utils.clean_search_query(f"{artist} - {title}")
        file_path = await userbot.search_text_via_target_bot(query)
        if not file_path:
            file_path = await userbot.search_global_music(artist, title)
        if not file_path:
            file_path = await utils.get_youtube_with_api(artist, title)
            
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ <b>Qidiruv boti orqali original fayl topilmadi.</b>")
            return
            
        temp_file_path = file_path
        
        # Clean artist/title with AI
        ai_cleaned = await utils.get_clean_details_with_ai(artist, title)
        clean_artist = utils._clean_single_string(ai_cleaned.get('artist') or artist) or "Trend MUSIC"
        clean_title = utils._clean_single_string(ai_cleaned.get('title') or title) or "Musiqa"
        
        # Clean metadata of the original file
        utils.write_clean_metadata(temp_file_path, clean_artist, clean_title)
        
        track_id = f"sched_bot_{random.randint(100000, 999999)}"
        persistent_file_path = os.path.join("downloads", f"sched_file_{track_id}.mp3")
        os.rename(temp_file_path, persistent_file_path)
        
        # Get old job arguments
        old_track = next_job.args[0]
        old_title = f"{old_track.get('artist', 'Unknown')} - {old_track.get('title', 'Unknown')}"
        
        # Modify the next job
        track_info = {
            'track_id': track_id,
            'artist': clean_artist,
            'title': clean_title,
            'direct_file_path': persistent_file_path
        }
        next_job.modify(args=[track_info])
        
        # Persist to database daily_schedule
        await database.update_schedule_entry(run_time, track_id, clean_artist, clean_title, persistent_file_path)
        
        # Update daily_plan
        global daily_plan
        for entry in daily_plan:
            if entry['time'] == time_str:
                entry['title'] = f"{clean_artist} - {clean_title} (Admin)"
                break
                
        await status_msg.edit_text(
            f"✅ <b>Jadval yangilandi!</b>\n\n"
            f"🕒 Vaqti: <b>{time_str}</b>\n"
            f"⏮️ Eski musiqa: <i>{old_title}</i>\n"
            f"⏭️ Yangi musiqa: <b>{clean_artist} - {clean_title}</b>"
        )
        await log_to_channel(f"📅 Jadval yangilandi (Vaqt: {time_str}): {old_title} ➡️ {clean_artist} - {clean_title}")
    except Exception as e:
        logger.error(f"process_and_schedule_direct_bot error: {e}")
        await status_msg.edit_text("❌ <b>Qayta ishlashda xatolik yuz berdi.</b> Tafsilotlar tizim loglarida.")


async def show_step2_keyboard(message, artist: str, title: str, method: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Hozir joylash (Tezkor)", callback_data="direct_post_now")
        ],
        [
            InlineKeyboardButton(text="📅 Jadvaldagi navbatdagisi o'rniga", callback_data="direct_post_sched")
        ],
        [
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="direct_cancel")
        ]
    ])
    text = (
        f"🎯 <b>Musiqa:</b> {artist} - {title}\n"
        f"⚙️ <b>Tur:</b> {'Originalni tozalash' if method == 'orig' else 'Bot orqali tozalash'}\n\n"
        "Joylash vaqtini tanlang:"
    )
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=keyboard)
    elif hasattr(message, "edit_text"):
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.reply(text, reply_markup=keyboard)

@dp.callback_query(lambda c: c.data and c.data.startswith("direct_"))
async def admin_direct_callback_handler(query: CallbackQuery, state: FSMContext):
    if not is_admin(query.from_user.id):
        await query.answer("Siz admin emassiz!", show_alert=True)
        return

    data = query.data
    
    if data == "direct_cancel":
        await state.clear()
        try: await query.message.delete()
        except: pass
        await query.answer("Bekor qilindi.")
        return
        
    state_data = await state.get_data()
    file_id = state_data.get("pending_file_id")
    raw_artist = state_data.get("pending_artist", "")
    raw_title = state_data.get("pending_title", "")
    
    if not file_id:
        await query.answer("Xatolik: Sessiya muddati tugadi. Iltimos musiqani qayta yuboring.", show_alert=True)
        await state.clear()
        try: await query.message.delete()
        except: pass
        return

    if data in ["direct_select_orig", "direct_select_bot"]:
        method = "orig" if "orig" in data else "bot"
        await state.update_data(pending_method=method)
        await query.answer()
        
        artist = raw_artist
        title = raw_title
        
        if not artist or not title:
            await query.message.edit_text("⏳ <b>Shazam orqali aniqlanmoqda...</b>")
            temp_path = f"downloads/temp_shazam_{random.randint(1000, 9999)}.mp3"
            try:
                os.makedirs("downloads", exist_ok=True)
                file = await bot.get_file(file_id)
                await bot.download_file(file.file_path, temp_path)
                
                shazam_result = await utils.identify_track_with_shazam(temp_path)
                if shazam_result:
                    artist = shazam_result['artist']
                    title = shazam_result['title']
            except Exception as e:
                logger.error(f"Direct Shazam identification error: {e}")
            finally:
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except: pass
                    
        if not artist or not title:
            await query.message.edit_text(
                "❓ <b>Musiqa ma'lumotlarini aniqlab bo'lmadi.</b>\n\n"
                "Iltimos, qo'shiqchi va qo'shiq nomini quyidagi formatda yozib yuboring:\n"
                "<code>Ijrochi - Qo'shiq nomi</code>"
            )
            await state.set_state(AdminStates.waiting_for_audio_metadata)
            return
            
        await state.update_data(pending_artist=artist, pending_title=title)
        await show_step2_keyboard(query.message, artist, title, method)
        
    elif data in ["direct_post_now", "direct_post_sched"]:
        artist = state_data.get("pending_artist")
        title = state_data.get("pending_title")
        method = state_data.get("pending_method", "orig")
        
        if not artist or not title:
            await query.answer("Xatolik: Ma'lumotlar topilmadi. Qayta yuboring.", show_alert=True)
            await state.clear()
            try: await query.message.delete()
            except: pass
            return

        if data == "direct_post_sched":
            # Verify schedule has active jobs
            post_jobs = []
            for job in scheduler.get_jobs():
                if job.id not in ['daily_planning', 'settings_checker']:
                    post_jobs.append(job)
            if not post_jobs:
                await query.answer("Jadvalda rejalashtirilgan musiqalar topilmadi! Iltimos, /rejalash orqali jadval tuzing.", show_alert=True)
                return

        await query.answer()
        await state.clear()
        
        if data == "direct_post_now":
            if method == "orig":
                await query.message.edit_text("⏳ <b>Original fayl qayta ishlanmoqda...</b>\nDemo kesilmoqda va kanalga joylanmoqda...")
                asyncio.create_task(process_and_post_direct_orig(query.message, file_id, artist, title))
            else:
                await query.message.edit_text(f"✅ Aniqlandi: <b>{artist} - {title}</b>\n🔍 Maqsadli botdan original fayl qidirilmoqda...")
                asyncio.create_task(process_and_post_direct_bot(query.message, artist, title))
        elif data == "direct_post_sched":
            if method == "orig":
                await query.message.edit_text("⏳ <b>Original fayl qayta ishlanmoqda va jadvalga joylanmoqda...</b>")
                asyncio.create_task(process_and_schedule_direct_orig(query.message, file_id, artist, title))
            else:
                await query.message.edit_text(f"✅ Aniqlandi: <b>{artist} - {title}</b>\n🔍 Maqsadli botdan fayl qidirilmoqda va jadvalga joylanmoqda...")
                asyncio.create_task(process_and_schedule_direct_bot(query.message, artist, title))

@dp.message(AdminStates.waiting_for_audio_metadata)
async def process_direct_metadata_input(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
        
    val = message.text.strip()
    
    # Try deleting the user's input message to keep chat clean
    try: await message.delete()
    except: pass
    
    if " - " not in val:
        await message.reply(
            "❌ Noto'g'ri format! Iltimos, quyidagi formatda kiritishingiz shart:\n"
            "<code>Ijrochi - Qo'shiq nomi</code>\n\n"
            "Masalan: <code>Sherali Jo'rayev - Gulbadan</code>"
        )
        return
        
    parts = val.split(" - ", 1)
    artist = parts[0].strip()
    title = parts[1].strip()
    
    state_data = await state.get_data()
    file_id = state_data.get("pending_file_id")
    method = state_data.get("pending_method", "orig")
    
    if not file_id:
        await message.reply("❌ Xatolik: Sessiya muddati tugadi yoki fayl topilmadi. Iltimos musiqani qaytadan yuboring.")
        await state.clear()
        return
        
    await state.update_data(pending_artist=artist, pending_title=title)
    
    # Show Step 2 Timing menu keyboard
    await show_step2_keyboard(message, artist, title, method)


@dp.message(lambda msg: msg.voice or msg.audio)
async def audio_search_handler(message: types.Message, state: FSMContext):
    # Intercept admin direct audio upload
    if is_admin(message.from_user.id):
        await state.clear()
        
        file_id = message.audio.file_id if message.audio else message.voice.file_id
        duration = message.audio.duration if message.audio else (message.voice.duration if message.voice else 0)
        performer = (message.audio.performer or "").strip() if message.audio else ""
        title = (message.audio.title or "").strip() if message.audio else ""
        
        await state.update_data(
            pending_file_id=file_id,
            pending_duration=duration,
            pending_artist=performer,
            pending_title=title
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📤 Originalini tozalash", callback_data="direct_select_orig")
            ],
            [
                InlineKeyboardButton(text="🔎 Bot orqali tozalash", callback_data="direct_select_bot")
            ],
            [
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="direct_cancel")
            ]
        ])
        
        await message.reply(
            "📥 <b>Musiqa qabul qilindi.</b> Faylni qanday qayta ishlashni xohlaysiz?",
            reply_markup=keyboard
        )
        return

    # 1. Agar foydalanuvchi tayyor audio fayl yuborgan bo'lsa va uning metama'lumotlari bo'lsa
    if message.audio:
        artist = (message.audio.performer or "").strip()
        title = (message.audio.title or "").strip()
        
        if artist or title:
            raw_query = f"{artist} - {title}".strip() if artist and title else (artist or title)
            query = utils.clean_search_query(raw_query)
            status_msg = await message.answer(f"🔍 Fayl ma'lumotlaridan qidirilmoqda: <b>{query}</b>...")
            try:
                # Target Bot orqali qidirish
                file_path = await userbot.search_text_via_target_bot(query)
                if not file_path:
                    file_path = await userbot.search_global_music("", query)
                if not file_path:
                    file_path = await utils.get_youtube_with_api("", query)
                    
                if file_path and os.path.exists(file_path):
                    await status_msg.delete()
                    await message.reply_audio(
                        audio=FSInputFile(file_path),
                        performer=artist or "Noma'lum",
                        title=title or "Musiqa",
                        caption=f"👉 @{(await bot.get_me()).username} orqali topildi!"
                    )
                    os.remove(file_path)
                    return
                else:
                    await status_msg.edit_text(f"❌ Afsuski, <b>{query}</b> nomi bo'yicha musiqa topilmadi. Iltimos, boshqa so'zlar bilan yozib ko'ring.")
                    return
            except Exception as e:
                logger.error(f"Audio metadata orqali qidiruvda xatolik: {e}")
                await status_msg.edit_text("❌ Musiqa qidirishda kutilmagan xatolik yuz berdi.")
                return

    # 2. Ovozli xabar yoki metama'lumotlari yo'q audio bo'lsa (Shazam orqali qidirish)
    if not utils.HAS_SHAZAM:
        await message.answer("❌ Tizimda ovoz orqali aniqlash vaqtincha faol emas.\n\nIltimos, musiqani topish uchun uning <b>nomini matn ko'rinishida</b> yozib yuboring! 🔎")
        return

    status_msg = await message.answer("🎙️ Ovoz tahlil qilinmoqda, iltimos kuting...")
    temp_path = f"downloads/search_{random.randint(1000, 9999)}.mp3"
    
    try:
        os.makedirs("downloads", exist_ok=True)
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, temp_path)
        
        shazam_result = await utils.identify_track_with_shazam(temp_path)
        
        if shazam_result:
            artist = shazam_result['artist']
            title = shazam_result['title']
            await status_msg.edit_text(f"✅ Aniqlandi: <b>{artist} - {title}</b>\nOriginal fayl yuklanmoqda...")
            
            query = utils.clean_search_query(f"{artist} - {title}")
            file_path = await userbot.search_text_via_target_bot(query)
            if not file_path:
                file_path = await userbot.search_global_music(artist, title)
            if not file_path:
                file_path = await utils.get_youtube_with_api(artist, title)
                
            if file_path and os.path.exists(file_path):
                await status_msg.delete()
                await message.reply_audio(
                    audio=FSInputFile(file_path),
                    performer=artist,
                    title=title,
                    caption=f"👉 @{(await bot.get_me()).username} orqali topildi!"
                )
                os.remove(file_path)
            else:
                await status_msg.edit_text("❌ Qo'shiq aniqlandi, lekin original faylini yuklab bo'lmadi.")
        else:
            await status_msg.edit_text("❌ Afsuski, ushbu ovozdan musiqani aniqlab bo'lmadi. Iltimos, uning nomini matn ko'rinishida yuboring! 🔎")
            
    except Exception as e:
        logger.error(f"Ovozli qidiruvda xatolik: {e}")
        await status_msg.edit_text("❌ Ovoz orqali qidirishda kutilmagan xatolik yuz berdi.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


async def set_main_menu(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="/start", description="🚀 Holat va Sozlamalar"),
        BotCommand(command="/admin", description="⚙️ Bot Admin Paneli"),
        BotCommand(command="/kanaldan", description="📢 Bitta post (Manual)"),
        BotCommand(command="/rejalash", description="🔄 Majburiy rejalash")
    ])


async def on_startup(bot: Bot):
    # Serverni tozalash
    logger.info("♻️ Server tozalanmoqda: downloads papkasi tozalanmoqda (scheduled papkasi saqlanadi)...")
    if os.path.exists("downloads"):
        for file in os.listdir("downloads"):
            if file == "scheduled":
                continue
            file_path = os.path.join("downloads", file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Fayl o'chirishda xatolik: {file_path} - {e}")
                
    # Ma'lumotlar bazasini sozlash (PostgreSQL)
    await database.setup_database()
    
    # Load database settings into config
    settings = await database.get_all_settings()
    if 'source_channels' in settings:
        config.SOURCE_CHANNELS = [ch.strip() for ch in re.split(r'[\s,]+', settings['source_channels']) if ch.strip()]
    if 'target_search_bot' in settings:
        config.TARGET_SEARCH_BOT = settings['target_search_bot']
        
    global LAST_SETTINGS
    LAST_SETTINGS = settings

    # Userbotni ishga tushirish
    userbot_success = await userbot.start()
    if not userbot_success:
        logger.warning("Userbot ishlamadi!")

    await setup_scheduler()
    await set_main_menu(bot)


async def setup_scheduler():
    scheduler.configure(timezone="Asia/Tashkent")
    plan_hour = int(await database.get_setting("planning_hour", "5"))

    scheduler.add_job(
        plan_daily_posts,
        'cron',
        hour=plan_hour,
        minute=0,
        id='daily_planning'
    )

    scheduler.add_job(
        check_schedule_update,
        'interval',
        seconds=5,
        id='settings_checker'
    )

    if not scheduler.running:
        scheduler.start()
        
    # Qayta ishga tushganda bazadagi rejalarni schedulerga yuklash
    asyncio.create_task(plan_daily_posts(force=False))


async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot o'chirildi.")
