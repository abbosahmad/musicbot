# userbot.py (Tuzatilgan versiya)

import asyncio
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from loguru import logger
from pyrogram import Client, enums
from pyrogram.types import Message
from pyrogram.errors import UserAlreadyParticipant

import config
import database
import utils

async def _safe_download(message, file_name: str, retries: int = 3, delay: int = 2) -> Optional[str]:
    dir_name = os.path.dirname(file_name)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    for attempt in range(1, retries + 1):
        try:
            temp_file = file_name + ".temp"
            if os.path.exists(temp_file):
                try: os.remove(temp_file)
                except: pass
                
            path = await message.download(file_name=file_name)
            if path and os.path.exists(str(path)) and os.path.getsize(str(path)) > 0:
                clean_mp3 = utils.ensure_mp3_format(str(path))
                return clean_mp3
        except Exception as e:
            logger.warning(f"Download attempt {attempt}/{retries} failed for {file_name}: {e}")
            if attempt < retries:
                await asyncio.sleep(delay)
    return None


class UserBot:
    def __init__(self):
        os.makedirs("session", exist_ok=True)
        self.app = Client(
            name="session/my_account",
            api_id=config.USERBOT_API_ID,
            api_hash=config.USERBOT_API_HASH,
            session_string=config.USERBOT_SESSION_STRING if config.USERBOT_SESSION_STRING else None,
        )



    async def start(self):
        try:
            if not config.USERBOT_SESSION_STRING and not os.path.exists("session/my_account.session"):
                logger.critical("USERBOT_SESSION_STRING yoki session/my_account.session topilmadi! Iltimos, avval login.py ni ishga tushiring.")
                return False
            
            logger.info("Userbot ulanmoqda...")
            await self.app.start()
            logger.success("Userbot muvaffaqiyatli ishga tushdi.")
            
            # Userbot ma'lumotlarini olish
            try:
                me = await self.app.get_me()
                logger.info(f"Userbot: @{me.username} ({me.first_name})")
            except Exception as e:
                logger.warning(f"Userbot ma'lumotlarini olishda xato: {e}")
            
            await self._join_source_channels()
            return True

        except Exception as e:
            logger.error(f"Userbot'ni ishga tushirishda xatolik: {e}")
            self.app = None
            return False
    
    async def _join_source_channels(self):
        if not self.app or not self.app.is_connected: return
        
        # Barcha manba kanallarni yig'amiz
        clean_db = re.split(r'[\s,]+', await database.get_setting("clean_source_channels", ""))
        direct_db = re.split(r'[\s,]+', await database.get_setting("direct_source_channels", ""))
        old_db = re.split(r'[\s,]+', await database.get_setting("source_channels", ""))
        
        all_channels = set(config.SOURCE_CHANNELS + [ch.strip() for ch in (clean_db + direct_db + old_db) if ch.strip()])
        for channel in all_channels:
            if not channel: continue
            try:
                await self.app.join_chat(channel)
                logger.info(f"Userbot '{channel}' kanaliga a'zo bo'ldi.")
                await asyncio.sleep(2)
            except UserAlreadyParticipant:
                 pass 
            except Exception as e:
                logger.warning(f"'{channel}' kanaliga qo'shilishda xatolik: {e}")

    def _process_message(self, message: Message) -> Optional[Dict]:
        if not (message.audio or message.voice): return None
        
        # --- QORA RO'YXAT TEKSHIRUVI ---
        # Kanal nomini tekshirish
        if hasattr(message.chat, 'username') and message.chat.username:
            for blocked_channel in config.BLACKLIST_CHANNELS:
                if blocked_channel.lower() in message.chat.username.lower():
                    return None
        
        # Caption va title'da qora ro'yxat so'zlarini tekshirish
        text_to_check = ""
        if message.caption: text_to_check += message.caption + " "
        if message.audio and message.audio.title: text_to_check += message.audio.title + " "
        if message.audio and message.audio.performer: text_to_check += message.audio.performer + " "
        
        for blocked_word in config.BLACKLIST_KEYWORDS:
            if blocked_word.lower() in text_to_check.lower():
                return None
        
        track_id = None
        artist = ""
        title = ""
        duration_ms = 0
        file_id = ""
        is_voice = False
        views = message.views or 0  # Ko'rishlar sonini olish
        reactions = 0
        if message.reactions and message.reactions.reactions:
            for r in message.reactions.reactions:
                reactions += r.count

        raw_caption = message.caption or ""
        if message.audio:
            audio = message.audio
            track_id = audio.file_unique_id
            raw_artist = audio.performer or ""
            raw_title = audio.title or audio.file_name or ""
            filename = audio.file_name or ""

            clean_artist, clean_title = utils.extract_clean_artist_and_title(
                raw_artist, raw_title, raw_caption, filename
            )

            artist = clean_artist
            title = clean_title if clean_title else raw_title
            duration_ms = (audio.duration or 0) * 1000
            file_id = audio.file_id
            is_voice = False
        elif message.voice:
            voice = message.voice
            track_id = voice.file_unique_id
            artist = ""
            title = raw_caption or "Unknown Voice"
            duration_ms = (voice.duration or 0) * 1000
            file_id = voice.file_id
            is_voice = True
        
        source_channel = "Noma'lum"
        if message.chat:
            if message.chat.username:
                source_channel = f"@{message.chat.username}"
            elif message.chat.title:
                source_channel = message.chat.title
            else:
                source_channel = str(message.chat.id)

        return {
            'track_id': track_id,
            'artist': artist,
            'title': title,
            'duration_ms': duration_ms,
            'file_id': file_id,
            'chat_id': message.chat.id,
            'message_id': message.id,
            'is_voice': is_voice,
            'views': views,
            'reactions': reactions,
            'date': message.date,
            'source_channel': source_channel,
            'raw_caption': raw_caption
        }

    async def get_new_music_from_channels(self, hours: int = 24) -> List[Dict]:
        if not self.app or not self.app.is_connected: return []
        logger.info(f"Manba kanallardan oxirgi {hours} soatdagi musiqalar qidirilmoqda...")
        collected_tracks = []
        time_limit = datetime.utcnow() - timedelta(hours=hours)

        # 1. Bot orqali yangilanadigan kanallar (Clean)
        clean_db = re.split(r'[\s,]+', await database.get_setting("clean_source_channels", ""))
        clean_channels = [ch.strip() for ch in clean_db if ch.strip()]
        if not clean_channels:
            clean_channels = config.CLEAN_SOURCE_CHANNELS

        # 2. To'g'ridan-to'g'ri olinadigan kanallar (Direct)
        direct_db = re.split(r'[\s,]+', await database.get_setting("direct_source_channels", ""))
        direct_channels = [ch.strip() for ch in direct_db if ch.strip()]
        if not direct_channels:
            direct_channels = config.DIRECT_SOURCE_CHANNELS

        # Agar ikkalasi ham bo'sh bo'lsa, umumiy source_channels dan olamiz
        if not clean_channels and not direct_channels:
            old_db = re.split(r'[\s,]+', await database.get_setting("source_channels", ""))
            clean_channels = [ch.strip() for ch in old_db if ch.strip()] or config.SOURCE_CHANNELS

        channel_configs = []
        for ch in clean_channels:
            channel_configs.append((ch, 'clean'))
        for ch in direct_channels:
            channel_configs.append((ch, 'direct'))

        for channel_id, mode in channel_configs:
            try:
                # Direct kanallar uchun 2 oy (1440 soat), Clean kanallar uchun parametr bo'yicha (masalan 168 soat)
                ch_hours = 1440 if mode == 'direct' else hours
                ch_time_limit = datetime.utcnow() - timedelta(hours=ch_hours)
                msg_limit = 2000 if mode == 'direct' else 800

                async for message in self.app.get_chat_history(channel_id, limit=msg_limit):
                    if message.date < ch_time_limit: break
                    media = message.audio or message.voice
                    # Kamida 1 daqiqa (60 soniya) bo'lgan musiqalarni olish
                    if media and media.duration and (media.duration >= 60):
                        processed = self._process_message(message)
                        if processed:
                            processed['mode'] = mode
                            collected_tracks.append(processed)
            except Exception as e:
                logger.error(f"'{channel_id}' kanalidan xabarlarni olishda xatolik: {e}")
        
        return collected_tracks
    
    async def get_recent_music_from_backup(self, hours: int = 48) -> List[Dict]:
        if not self.app or not self.app.is_connected: return []
        logger.warning(f"Zaxira kanaldan oxirgi {hours} soatdagi musiqalar qidirilmoqda...")
        found_tracks, time_limit = [], datetime.utcnow() - timedelta(hours=hours)
        try:
            async for message in self.app.get_chat_history(config.BACKUP_CHANNEL_ID, limit=300):
                if message.date < time_limit: break
                media = message.audio or message.voice
                if media:
                    track_info = self._process_message(message)
                    if track_info and not await database.is_track_posted(track_info.get('track_id')):
                        found_tracks.append(track_info)
        except Exception as e:
            logger.error(f"Zaxira kanaldan o'qishda xatolik: {e}")
        return found_tracks
    
    async def get_old_music_from_sources(self) -> List[Dict]:
        return [] # Bu endi kerak emas

    async def forward_tracks_to_backup(self, tracks: List[Dict]):
        pass # Bu ham hozircha shart emas

    async def download_music(self, chat_id: int, message_id: int, file_path: str) -> Optional[str]:
        if not self.app or not self.app.is_connected: return None
        try:
            logger.info(f"Fayl ruxsatnomasini yangilash uchun xabar ({chat_id}:{message_id}) qayta so'ralmoqda...")
            fresh_message = await self.app.get_messages(chat_id, message_id)
            
            if not fresh_message or (not fresh_message.audio and not fresh_message.voice):
                logger.error("Xabarni qayta olib bo'lmadi.")
                return None

            downloaded_path = await _safe_download(fresh_message, file_path)
            
            if downloaded_path and os.path.exists(str(downloaded_path)) and os.path.getsize(str(downloaded_path)) > 0:
                return str(downloaded_path)
            else:
                return None
        except Exception as e:
            logger.error(f"Fayl yuklashda Pyrogram xatoligi: {e}")
            return None

    async def search_via_target_bot(self, chat_id: int, message_id: int) -> Optional[str]:
        """
        Reklamali musiqani maqsadli qidiruv botiga (masalan, @Zoryuklabot) forward qilib original toza faylni oladi.
        """
        if not self.app or not self.app.is_connected:
            return None
            
        target_search_bot = await database.get_setting("target_search_bot", "@Zoryuklabot")
        logger.info(f"Musiqa maqsadli botga forward qilinmoqda: {target_search_bot}")
        
        try:
            # Bot chatini olish
            target_chat = await self.app.get_chat(target_search_bot)
            target_chat_id = target_chat.id
            
            # Forwarddan oldingi so'nggi xabar ID-sini olish
            last_msg_id = 0
            async for msg in self.app.get_chat_history(target_chat_id, limit=1):
                last_msg_id = msg.id
                
            # Xabarni forward qilish
            await self.app.forward_messages(
                chat_id=target_chat_id,
                from_chat_id=chat_id,
                message_ids=message_id
            )
            
            # Botdan javob ro'yxatini kutish
            response_msg = None
            for _ in range(12): # Maksimal 12 soniya
                await asyncio.sleep(1)
                async for msg in self.app.get_chat_history(target_chat_id, limit=3):
                    if msg.id > last_msg_id and msg.from_user and msg.from_user.is_bot:
                        response_msg = msg
                        break
                if response_msg:
                    break
            
            if not response_msg:
                logger.warning("Maqsadli qidiruv botidan javob kelmadi.")
                return None
                
            logger.info(f"Maqsadli botdan javob olindi: {response_msg.id}")
            last_msg_id_before_click = response_msg.id
            
            # Inline tugmalarni tekshirish (Eng yaxshi variantni tanlash)
            target_btn_text = utils.choose_best_result_number(response_msg.text or response_msg.caption)
            logger.info(f"Target bot natijalari tahlil qilindi. Tanlangan variant: {target_btn_text}")
            
            if response_msg.reply_markup and response_msg.reply_markup.inline_keyboard:
                btn_row = 0
                btn_col = 0
                found = False
                for r_idx, row in enumerate(response_msg.reply_markup.inline_keyboard):
                    for c_idx, btn in enumerate(row):
                        b_txt = btn.text.strip()
                        if b_txt == target_btn_text or b_txt.startswith(f"{target_btn_text} ") or b_txt.startswith(f"{target_btn_text}.") or b_txt == f"[{target_btn_text}]":
                            btn_row = r_idx
                            btn_col = c_idx
                            found = True
                            break
                    if found:
                        break
                        
                logger.info(f"Tugma bosilmoqda: [{btn_row}, {btn_col}] (Matn: {target_btn_text})")
                await response_msg.click(btn_col, btn_row)
            else:
                # Agar inline tugma bo'lmasa, matn ko'rinishida yuboramiz
                logger.info(f"Inline tugma topilmadi, matnli '{target_btn_text}' javobi yuborilmoqda.")
                await self.app.send_message(target_chat_id, target_btn_text, reply_to_message_id=response_msg.id)
                
            # Maqsadli botdan audio fayl kelishini kutish
            audio_msg = None
            for _ in range(15): # Maksimal 15 soniya
                await asyncio.sleep(1)
                async for msg in self.app.get_chat_history(target_chat_id, limit=3):
                    if msg.id > last_msg_id_before_click and msg.audio:
                        audio_msg = msg
                        break
                if audio_msg:
                    break
                    
            if audio_msg and audio_msg.audio:
                file_name = f"downloads/original_{audio_msg.audio.file_unique_id}.mp3"
                path = await _safe_download(audio_msg, file_name)
                if path:
                    logger.success(f"✅ Original toza musiqa muvaffaqiyatli yuklandi: {path}")
                    return path
            
            logger.warning("Maqsadli bot audio fayl qaytarmadi.")
            return None
            
        except Exception as e:
            logger.error(f"Maqsadli bot orqali qidirishda xatolik: {e}")
            return None

    async def search_text_via_target_bot(self, query: str) -> Optional[str]:
        """
        Matnli so'rovni maqsadli qidiruv botiga (masalan, @Zoryuklabot) yuborib original toza faylni oladi.
        """
        if not self.app or not self.app.is_connected:
            return None
            
        # So'rovni yuborishdan oldin tozalash
        query = utils.clean_search_query(query)
        if not query or not query.strip():
            return None
            
        target_search_bot = await database.get_setting("target_search_bot", "@Zoryuklabot")
        logger.info(f"Matnli so'rov maqsadli botga yuborilmoqda: {target_search_bot} | So'rov: {query}")
        
        try:
            target_chat = await self.app.get_chat(target_search_bot)
            target_chat_id = target_chat.id
            
            last_msg_id = 0
            async for msg in self.app.get_chat_history(target_chat_id, limit=1):
                last_msg_id = msg.id
                
            # So'rovni matn ko'rinishida yuborish
            await self.app.send_message(chat_id=target_chat_id, text=query)
            
            response_msg = None
            for _ in range(12):
                await asyncio.sleep(1)
                async for msg in self.app.get_chat_history(target_chat_id, limit=3):
                    if msg.id > last_msg_id and msg.from_user and msg.from_user.is_bot:
                        response_msg = msg
                        break
                if response_msg:
                    break
            
            if not response_msg:
                return None
                
            last_msg_id_before_click = response_msg.id
            
            # Inline tugmalarni tekshirish (Eng yaxshi variantni tanlash)
            target_btn_text = utils.choose_best_result_number(response_msg.text or response_msg.caption, query=query)
            logger.info(f"Target bot natijalari tahlil qilindi (Matn). Tanlangan variant: {target_btn_text}")
            
            if response_msg.reply_markup and response_msg.reply_markup.inline_keyboard:
                btn_row = 0
                btn_col = 0
                found = False
                for r_idx, row in enumerate(response_msg.reply_markup.inline_keyboard):
                    for c_idx, btn in enumerate(row):
                        b_txt = btn.text.strip()
                        if b_txt == target_btn_text or b_txt.startswith(f"{target_btn_text} ") or b_txt.startswith(f"{target_btn_text}.") or b_txt == f"[{target_btn_text}]":
                            btn_row = r_idx
                            btn_col = c_idx
                            found = True
                            break
                    if found:
                        break
                logger.info(f"Tugma bosilmoqda: [{btn_row}, {btn_col}] (Matn: {target_btn_text})")
                await response_msg.click(btn_col, btn_row)
            else:
                logger.info(f"Inline tugma topilmadi, matnli '{target_btn_text}' javobi yuborilmoqda.")
                await self.app.send_message(target_chat_id, target_btn_text, reply_to_message_id=response_msg.id)
                
            audio_msg = None
            for _ in range(15):
                await asyncio.sleep(1)
                async for msg in self.app.get_chat_history(target_chat_id, limit=3):
                    if msg.id > last_msg_id_before_click and msg.audio:
                        audio_msg = msg
                        break
                if audio_msg:
                    break
            if audio_msg and audio_msg.audio:
                file_name = f"downloads/original_{audio_msg.audio.file_unique_id}.mp3"
                path = await _safe_download(audio_msg, file_name)
                return path
            
            return None
        except Exception as e:
            logger.error(f"Matn bo'yicha qidiruvda xatolik: {e}")
            return None
