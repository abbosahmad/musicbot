# userbot.py (Yangi versiya)

import asyncio
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from loguru import logger
from pyrogram import Client
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

    async def start(self):
        try:
            if not config.USERBOT_SESSION_STRING:
                logger.critical("USERBOT_SESSION_STRING topilmadi! Iltimos, avval login.py ni ishga tushiring.")
                exit()
            
            await self.app.start()
            logger.success("Userbot muvaffaqiyatli ishga tushdi.")
            await self._join_source_channels()

        except Exception as e:
            logger.error(f"Userbot'ni ishga tushirishda xatolik: {e}")
            self.app = None
    
    async def _join_source_channels(self):
        if not self.app or not self.app.is_connected: return
        all_channels = config.SOURCE_CHANNELS + [config.BACKUP_CHANNEL_ID]
        for channel in all_channels:
            if not channel: continue
            try:
                await self.app.join_chat(channel)
                logger.info(f"Userbot '{channel}' kanaliga a'zo bo'ldi.")
                await asyncio.sleep(2)
            except UserAlreadyParticipant:
                 logger.info(f"Userbot allaqachon '{channel}' kanaliga a'zo.")
            except Exception as e:
                logger.warning(f"'{channel}' kanaliga qo'shilishda xatolik: {e}")

    def _process_message(self, message: Message) -> Optional[Dict]:
        if not message.audio: return None
        audio = message.audio
        
        # O'ZGARTIRILDI: Xabarning ID'sini va chat ID'sini saqlab qolamiz
        return {
            'track_id': audio.file_unique_id,
            'artist': audio.performer,
            'title': audio.title or audio.file_name,
            'duration_ms': (audio.duration or 0) * 1000,
            'file_id': audio.file_id,
            'chat_id': message.chat.id,    # YANGI
            'message_id': message.id,      # YANGI
            'message': message             # Bu kerak bo'lmay qolishi mumkin, lekin qoldiramiz
        }

    async def get_new_music_from_channels(self) -> List[Dict]:
        if not self.app or not self.app.is_connected: return []
        logger.info(f"{len(config.SOURCE_CHANNELS)} ta manba kanaldan yangi musiqa qidirilmoqda...")
        collected_tracks, one_day_ago = [], datetime.now() - timedelta(days=1)

        for channel_id in config.SOURCE_CHANNELS:
            try:
                async for message in self.app.get_chat_history(channel_id, limit=200):
                    if message.date < one_day_ago: break
                    if message.audio and message.audio.duration and (message.audio.duration > 120):
                        processed = self._process_message(message)
                        if processed and not await database.is_track_posted(processed['track_id']):
                            collected_tracks.append(processed)
            except Exception as e:
                logger.error(f"'{channel_id}' kanalidan xabarlarni olishda xatolik: {e}")
        return collected_tracks
    
    async def get_recent_music_from_backup(self, hours: int = 48) -> List[Dict]:
        # Bu funksiya o'zgarishsiz qoladi...
        if not self.app or not self.app.is_connected: return []
        logger.warning(f"Zaxira kanaldan oxirgi {hours} soatdagi musiqalar qidirilmoqda...")
        found_tracks, time_limit = [], datetime.now() - timedelta(hours=hours)
        try:
            async for message in self.app.get_chat_history(config.BACKUP_CHANNEL_ID, limit=300):
                if message.date < time_limit: break
                if message.audio:
                    track_info = self._process_message(message)
                    if track_info and not await database.is_track_posted(track_info.get('track_id')):
                        found_tracks.append(track_info)
        except Exception as e:
            logger.error(f"Zaxira kanaldan o'qishda xatolik: {e}")
        logger.success(f"Zaxiradan {len(found_tracks)} ta yangi musiqa topildi.")
        return found_tracks
    
    async def get_old_music_from_sources(self) -> List[Dict]:
        # Bu funksiya o'zgarishsiz qoladi...
        if not self.app or not self.app.is_connected: return []
        logger.warning("ENG OXIRGI CHORA: Manba kanallar tarixidan eski musiqalar qidirilmoqda...")
        collected_tracks = []
        for channel_id in config.SOURCE_CHANNELS:
            try:
                async for message in self.app.get_chat_history(channel_id, limit=500):
                    if message.audio and message.audio.duration and (message.audio.duration > 120):
                        processed = self._process_message(message)
                        if processed and not await database.is_track_posted(processed['track_id']):
                            collected_tracks.append(processed)
                            if len(collected_tracks) >= 5: break
            except Exception as e:
                logger.error(f"'{channel_id}' kanalining tarixini o'qishda xatolik: {e}")
            if len(collected_tracks) >= 5: break
        if collected_tracks:
            logger.success(f"Manba kanallar tarixidan {len(collected_tracks)} ta eski musiqa topildi.")
        else:
            logger.error("Manba kanallar tarixidan ham post qilinmagan musiqa topilmadi.")
        return collected_tracks

    async def forward_tracks_to_backup(self, tracks: List[Dict]):
        if not self.app or not self.app.is_connected or not tracks: return
        logger.info(f"{len(tracks)} ta ortiqcha trekni zaxira kanalga yuborish boshlandi...")
        try:
            # Treklarni chat_id bo'yicha guruhlash
            tracks_by_chat = {}
            for track in tracks:
                chat_id = track['chat_id']
                if chat_id not in tracks_by_chat:
                    tracks_by_chat[chat_id] = []
                tracks_by_chat[chat_id].append(track['message_id'])
            
            # Har bir chat uchun alohida forward qilish
            for from_chat_id, message_ids in tracks_by_chat.items():
                await self.app.forward_messages(
                    chat_id=config.BACKUP_CHANNEL_ID,
                    from_chat_id=from_chat_id,
                    message_ids=message_ids)
                await asyncio.sleep(1)
            logger.success(f"{len(tracks)} ta trek zaxira kanalga muvaffaqiyatli saqlandi.")
        except Exception as e:
            logger.error(f"Trekni zaxiraga yuborishda xatolik: {e}")

    # O'ZGARTIRILDI: Bu funksiya endi xabar obyektini emas, ID'larni qabul qiladi
    async def download_music(self, chat_id: int, message_id: int, file_path: str) -> Optional[str]:
        if not self.app or not self.app.is_connected: return None
        try:
            # YECHIM: Faylni yuklashdan avval xabarni qaytadan so'rab olamiz.
            # Bu file_reference'ni yangilaydi.
            logger.info(f"Fayl ruxsatnomasini yangilash uchun xabar ({chat_id}:{message_id}) qayta so'ralmoqda...")
            fresh_message = await self.app.get_messages(chat_id, message_id)
            
            if not fresh_message or not fresh_message.audio:
                logger.error("Xabarni qayta olib bo'lmadi yoki unda audio yo'q.")
                return None

            # Endi yangilangan xabar obyektidan faylni yuklaymiz
            downloaded_path = await fresh_message.download(file_name=file_path)
            
            if downloaded_path and os.path.exists(str(downloaded_path)) and os.path.getsize(str(downloaded_path)) > 0:
                return str(downloaded_path)
            else:
                logger.error(f"Pyrogram faylni yuklamadi yoki fayl bo'sh qoldi. Path: {downloaded_path}")
                return None
        except Exception as e:
            # Xatolikni to'liq ko'rsatish uchun o'zgartirish
            logger.error(f"Fayl yuklashda Pyrogram xatoligi: {e}")
            return None