# userbot.py (Tuzatilgan versiya)

import asyncio
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from loguru import logger
from pyrogram import Client, enums
from pyrogram.types import Message
from pyrogram.errors import UserAlreadyParticipant

import config
import database

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
            if not config.USERBOT_SESSION_STRING:
                logger.critical("USERBOT_SESSION_STRING topilmadi! Iltimos, avval login.py ni ishga tushiring.")
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

        if message.audio:
            audio = message.audio
            track_id = audio.file_unique_id
            artist = audio.performer
            title = audio.title or audio.file_name
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
        
        return {
            'track_id': track_id,
            'artist': artist,
            'title': title,
            'duration_ms': duration_ms,
            'file_id': file_id,
            'chat_id': message.chat.id,
            'message_id': message.id,
            'is_voice': is_voice,
            'views': views
        }

    async def get_new_music_from_channels(self, hours: int = 24) -> List[Dict]:
        if not self.app or not self.app.is_connected: return []
        logger.info(f"Manba kanallardan oxirgi {hours} soatdagi musiqalar qidirilmoqda...")
        collected_tracks = []
        time_limit = datetime.now() - timedelta(hours=hours)

        # Manba kanallarni ma'lumotlar bazasidan olamiz (yoki config dan agar bo'sh bo'lsa)
        db_channels = database.get_setting("source_channels", "").split(",")
        channels_to_check = [ch.strip() for ch in db_channels if ch.strip()]
        
        if not channels_to_check:
            channels_to_check = config.SOURCE_CHANNELS

        for channel_id in channels_to_check:
            try:
                # logger.info(f"Kanal tekshirilmoqda: {channel_id}")
                async for message in self.app.get_chat_history(channel_id, limit=200):
                    if message.date < time_limit: break
                    media = message.audio or message.voice
                    # Davomiyligi 60 soniyadan uzun bo'lgan musiqalarni olish
                    if media and media.duration and (media.duration > 60):
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
        found_tracks, time_limit = [], datetime.now() - timedelta(hours=hours)
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
