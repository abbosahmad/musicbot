"""Navbatdagi post turini tanlash va uni kanalga (yoki preview uchun adminga) yuborish."""
import html
import random
from typing import Dict, Optional, Tuple, Union

from aiogram import Bot
from aiogram.types import BufferedInputFile, Message
from loguru import logger

from . import settings, tts, writer
from .storage import Storage

CAPTION_LIMIT = 1024
CATEGORIES = ("quote", "clip", "voice", "music")


def available_categories(counts: Dict[str, Dict[str, int]], tts_ok: bool) -> list:
    available = ["quote"]
    if counts.get("clip", {}).get("total"):
        available.append("clip")
    if counts.get("voice", {}).get("total") or tts_ok:
        available.append("voice")
    if counts.get("music", {}).get("total"):
        available.append("music")
    return available


def choose_category(available: list, mix: Dict[str, int], last: Optional[str],
                    rng: random.Random = random) -> str:
    """Og'irlik bo'yicha tasodifiy tanlov; iloji bo'lsa oldingi tur ketma-ket takrorlanmaydi."""
    candidates = [c for c in available if mix.get(c, 0) > 0] or ["quote"]
    if len(candidates) > 1 and last in candidates:
        candidates.remove(last)
    weights = [mix.get(c, 1) or 1 for c in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def _with_signature(text: str) -> str:
    if settings.SIGNATURE:
        text = f"{text}\n\n{html.escape(settings.SIGNATURE)}" if text else html.escape(settings.SIGNATURE)
    return text


def format_line(text: str) -> str:
    """Kanal uslubi: bitta qisqa jumla blockquote ichida."""
    text = text if len(text) <= CAPTION_LIMIT - 50 else text[:CAPTION_LIMIT - 51] + "…"
    return _with_signature(f"<blockquote>{html.escape(text)}</blockquote>")


def media_caption(media: Dict) -> Optional[str]:
    """Admin media bilan caption yuborgan bo'lsa - o'shani o'zgarishsiz (formatlash bilan) qo'yamiz."""
    return _with_signature(media["note"]) if media.get("note") else None


class Publisher:
    def __init__(self, bot: Bot, storage: Storage):
        self.bot = bot
        self.storage = storage

    async def next_category(self) -> str:
        counts = await self.storage.count_by_category()
        available = available_categories(counts, tts.is_available())
        return choose_category(available, settings.MIX, await self.storage.last_category())

    async def publish(self, category: Optional[str] = None, chat_id: Union[int, str, None] = None,
                      media_id: Optional[int] = None) -> Tuple[bool, str]:
        """chat_id berilmasa kanalga joylaydi va tarixga yozadi; berilsa - faqat namuna (preview)."""
        is_preview = chat_id is not None
        target = chat_id if is_preview else settings.CHANNEL_ID
        if not target:
            return False, "AGENT_CHANNEL_ID sozlanmagan"

        media = await self.storage.get_media(media_id) if media_id else None
        if media:
            category = media["category"]
        category = category or await self.next_category()
        recent = await self.storage.recent_texts()

        try:
            if category == "quote":
                msg, text, used = await self._send_quote(target, recent)
            elif category == "clip":
                msg, text, used = await self._send_clip(target, recent, media)
            elif category == "voice":
                msg, text, used = await self._send_voice(target, recent, media)
            elif category == "music":
                msg, text, used = await self._send_music(target, recent, media)
            else:
                return False, f"Noma'lum tur: {category}"
        except Exception as e:
            logger.exception(f"Post yuborishda xato ({category})")
            return False, f"Xato: {e}"

        if msg is None:
            return False, text

        if not is_preview:
            await self.storage.add_post(category, text, used["id"] if used else None, msg.message_id)
            if used:
                await self.storage.mark_used(used["id"])
        logger.info(f"Post yuborildi: {category} -> {target}")
        return True, category

    async def _send_quote(self, target, recent):
        text = await writer.write_line("quote", recent)
        msg = await self.bot.send_message(target, format_line(text))
        return msg, text, None

    async def _caption_for(self, media: Dict, category: str, recent, hint: str = "") -> Tuple[str, str]:
        """(caption_html, tarix uchun matn)"""
        caption = media_caption(media)
        if caption:
            return caption, media["note"]
        text = await writer.write_line(category, recent, hint)
        return format_line(text), text

    async def _send_clip(self, target, recent, media=None):
        media = media or await self.storage.pick_media("clip")
        if not media:
            return None, "Kutubxonada kino parcha yo'q", None
        caption, text = await self._caption_for(media, "clip", recent)
        if media["kind"] == "video":
            msg = await self.bot.send_video(target, media["file_id"], caption=caption)
        elif media["kind"] == "animation":
            msg = await self.bot.send_animation(target, media["file_id"], caption=caption)
        else:
            # Dumaloq videoda caption bo'lmaydi - matnni alohida xabar qilib yuboramiz
            msg = await self.bot.send_video_note(target, media["file_id"])
            await self.bot.send_message(target, caption)
        return msg, text, media

    async def _send_voice(self, target, recent, media=None):
        forced = media is not None
        media = media or await self.storage.pick_media("voice")
        # Kutubxonadagi barcha ovozlar ishlatilgan bo'lsa va TTS bor bo'lsa - yangi ovoz yaratamiz
        if not forced and (media is None or media["used_count"] > 0) and tts.is_available():
            data = await writer.write_voice_script(recent)
            audio = await tts.synthesize(data["script"])
            if audio:
                caption = format_line(data["caption"]) if data["caption"] else (_with_signature("") or None)
                msg = await self.bot.send_voice(
                    target, BufferedInputFile(audio, filename="voice.ogg"), caption=caption
                )
                return msg, data["caption"] or data["script"], None
        if not media:
            return None, "Ovozli xabar yo'q va TTS ishlamadi", None
        caption, text = await self._caption_for(media, "voice", recent)
        msg = await self.bot.send_voice(target, media["file_id"], caption=caption)
        return msg, text, media

    async def _send_music(self, target, recent, media=None):
        media = media or await self.storage.pick_media("music")
        if not media:
            return None, "Kutubxonada musiqa yo'q", None
        hint = f"Qo'shiq: {media['title']}" if media["title"] else ""
        caption, text = await self._caption_for(media, "music", recent, hint)
        msg = await self.bot.send_audio(target, media["file_id"], caption=caption)
        return msg, text, media
