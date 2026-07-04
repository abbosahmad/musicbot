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

class UserBot:
    def __init__(self):
        os.makedirs("session", exist_ok=True)
        self.app = Client(
            name="session/my_account",
            api_id=config.USERBOT_API_ID,
            api_hash=config.USERBOT_API_HASH,
            session_string=config.USERBOT_SESSION_STRING if config.USERBOT_SESSION_STRING else None,
        )

    async def search_global_music(self, artist: str, title: str) -> Optional[str]:
        """
        Telegram Global Qidiruv orqali musiqa topish va yuklash
        """
        if not self.app or not self.app.is_connected: return None
        
        query = f"{artist} - {title}"
        logger.info(f"Telegram Global Qidiruv: '{query}'")
        
        try:
            best_msg = None
            max_size = 0
            
            # 10 ta natijani tekshiramiz
            async for message in self.app.search_global(query, filter=enums.MessagesFilter.AUDIO, limit=10):
                if message.audio:
                    # Fayl hajmi va davomiyligini tekshirish (juda kichik yoki katta bo'lmasligi kerak)
                    duration = message.audio.duration or 0
                    size = message.audio.file_size or 0
                    
                    if duration > 60 and size > 2 * 1024 * 1024: # 1 min va 2MB dan katta
                        # Eng katta faylni tanlaymiz (sifatliroq bo'lishi ehtimoli yuqori)
                        if size > max_size:
                            max_size = size
                            best_msg = message
            
            if best_msg:
                file_name = f"downloads/global_{best_msg.audio.file_unique_id}.mp3"
                logger.info(f"Topildi: {best_msg.audio.performer} - {best_msg.audio.title} ({max_size / 1024 / 1024:.2f} MB)")
                
                path = await best_msg.download(file_name=file_name)
                if path:
                    logger.success("✅ Global Qidiruvdan yuklandi!")
                    return path
            
            logger.warning("Global Qidiruvda mos variant topilmadi.")
            return None
            
        except Exception as e:
            logger.error(f"Global Qidiruv xatosi: {e}")
            return None

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
        all_channels = config.SOURCE_CHANNELS 
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
                    # logger.info(f"Qora ro'yxatdagi kanal: {message.chat.username}")
                    return None
        
        # Caption va title'da qora ro'yxat so'zlarini tekshirish
        text_to_check = ""
        if message.caption: text_to_check += message.caption + " "
        if message.audio and message.audio.title: text_to_check += message.audio.title + " "
        if message.audio and message.audio.performer: text_to_check += message.audio.performer + " "
        
        for blocked_word in config.BLACKLIST_KEYWORDS:
            if blocked_word.lower() in text_to_check.lower():
                # logger.info(f"Qora ro'yxatdagi so'z topildi: {blocked_word}")
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

        if message.audio:
            audio = message.audio
            track_id = audio.file_unique_id
            raw_artist = audio.performer or ""
            raw_title = audio.title or audio.file_name or ""
            caption = message.caption or ""
            filename = audio.file_name or ""

            clean_artist, clean_title = utils.extract_clean_artist_and_title(
                raw_artist, raw_title, caption, filename
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
            title = message.caption or "Unknown Voice"
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
            'source_channel': source_channel
        }

    async def get_new_music_from_channels(self, hours: int = 24) -> List[Dict]:
        if not self.app or not self.app.is_connected: return []
        logger.info(f"Manba kanallardan oxirgi {hours} soatdagi musiqalar qidirilmoqda...")
        collected_tracks = []
        time_limit = datetime.utcnow() - timedelta(hours=hours)

        # Manba kanallarni ma'lumotlar bazasidan olamiz (yoki config dan agar bo'sh bo'lsa)
        db_channels = re.split(r'[\s,]+', await database.get_setting("source_channels", ""))
        channels_to_check = [ch.strip() for ch in db_channels if ch.strip()]
        
        if not channels_to_check:
            channels_to_check = config.SOURCE_CHANNELS

        for channel_id in channels_to_check:
            try:
                # logger.info(f"Kanal tekshirilmoqda: {channel_id}")
                async for message in self.app.get_chat_history(channel_id, limit=800):
                    if message.date < time_limit: break
                    media = message.audio or message.voice
                    # Davomiyligi 120 soniyadan kam bo'lmagan musiqalarni olish (kamida 2 daqiqa)
                    if media and media.duration and (media.duration >= 120):
                        processed = self._process_message(message)
                        if processed:
                            # Bu yerda bazani tekshirmaymiz, uni main.py da qilamiz
                            # shunda umumiy ro'yxatni sort qilish oson bo'ladi
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

            downloaded_path = await fresh_message.download(file_name=file_path)
            
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
            
            # Inline tugmalarni tekshirish (1-musiqani tanlash)
            if response_msg.reply_markup and response_msg.reply_markup.inline_keyboard:
                btn_row = 0
                btn_col = 0
                found = False
                for r_idx, row in enumerate(response_msg.reply_markup.inline_keyboard):
                    for c_idx, btn in enumerate(row):
                        if btn.text.strip() == "1":
                            btn_row = r_idx
                            btn_col = c_idx
                            found = True
                            break
                    if found:
                        break
                        
                logger.info(f"Tugma bosilmoqda: [{btn_row}, {btn_col}]")
                await response_msg.click(btn_col, btn_row)
            else:
                # Agar inline tugma bo'lmasa, matn ko'rinishida '1' deb yuboramiz
                logger.info("Inline tugma topilmadi, matnli '1' javobi yuborilmoqda.")
                await self.app.send_message(target_chat_id, "1", reply_to_message_id=response_msg.id)
                
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
                path = await audio_msg.download(file_name=file_name)
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
            
            if response_msg.reply_markup and response_msg.reply_markup.inline_keyboard:
                btn_row = 0
                btn_col = 0
                found = False
                for r_idx, row in enumerate(response_msg.reply_markup.inline_keyboard):
                    for c_idx, btn in enumerate(row):
                        if btn.text.strip() == "1":
                            btn_row = r_idx
                            btn_col = c_idx
                            found = True
                            break
                    if found:
                        break
                await response_msg.click(btn_col, btn_row)
            else:
                await self.app.send_message(target_chat_id, "1", reply_to_message_id=response_msg.id)
                
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
                path = await audio_msg.download(file_name=file_name)
                return path
            
            return None
        except Exception as e:
            logger.error(f"Matn bo'yicha qidiruvda xatolik: {e}")
            return None
