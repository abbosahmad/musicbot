"""Matnni Telegram ovozli xabariga (OGG/Opus) aylantirish."""
from typing import Optional

from loguru import logger
from openai import AsyncOpenAI

from . import settings


def is_available() -> bool:
    return settings.TTS_ENABLED and bool(settings.TTS_API_KEY)


async def synthesize(text: str) -> Optional[bytes]:
    """OGG/Opus baytlarini qaytaradi (Telegram send_voice to'g'ridan-to'g'ri qabul qiladi)."""
    if not is_available():
        return None
    try:
        client = AsyncOpenAI(api_key=settings.TTS_API_KEY, base_url=settings.TTS_BASE_URL, timeout=60.0)
        resp = await client.audio.speech.create(
            model=settings.TTS_MODEL,
            voice=settings.TTS_VOICE,
            input=text,
            response_format="opus",
        )
        return resp.content
    except Exception as e:
        logger.error(f"TTS xatosi: {e}")
        return None
