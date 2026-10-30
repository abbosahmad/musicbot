import os
from pathlib import Path

from dotenv import load_dotenv

# Loyiha ildizidagi .env faylini yuklash (asosiy bot bilan bir xil fayl)
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / '.env')


def _parse_channel_id(val):
    if not val:
        return 0
    try:
        return int(val)
    except ValueError:
        return val.strip()


def _parse_mix(raw: str) -> dict:
    """'quote:3,clip:2' -> {'quote': 3, 'clip': 2}"""
    mix = {}
    for part in raw.split(','):
        if ':' not in part:
            continue
        name, weight = part.split(':', 1)
        try:
            mix[name.strip()] = max(0, int(weight))
        except ValueError:
            continue
    return mix


# --- Telegram ---
# Alohida bot token tavsiya etiladi: bitta tokenni ikki jarayon bir vaqtda polling qila olmaydi.
BOT_TOKEN = os.getenv("AGENT_BOT_TOKEN") or os.getenv("ADMIN_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("AGENT_ADMIN_ID") or os.getenv("ADMIN_USER_ID") or 0)
CHANNEL_ID = _parse_channel_id(os.getenv("AGENT_CHANNEL_ID") or os.getenv("MAIN_CHANNEL_ID"))
# Har bir post oxiriga qo'shiladigan imzo, masalan: "🌙 @mening_kanalim"
SIGNATURE = os.getenv("AGENT_SIGNATURE", "")

# --- Jadval ---
TIMEZONE = os.getenv("AGENT_TIMEZONE", "Asia/Tashkent")
POST_TIMES = [t.strip() for t in os.getenv("AGENT_POST_TIMES", "08:00,11:00,14:00,17:00,20:00,22:30").split(',') if t.strip()]
# Post vaqtiga +/- tasodifiy siljish (soniya), kanal "jonli" ko'rinishi uchun
JITTER_SECONDS = int(os.getenv("AGENT_JITTER_SECONDS", "300"))
# Post turlarining ulushi (og'irligi)
MIX = _parse_mix(os.getenv("AGENT_MIX", "clip:5,voice:2,music:2,quote:1"))

# --- Mavzu / uslub ---
TOPICS = os.getenv("AGENT_TOPICS", "sevgi, sadoqat, oila, nasib, sog'inch, juftlik baxti")
# Post matnlari yozuvi: "cyrillic" yoki "latin"
SCRIPT = os.getenv("AGENT_SCRIPT", "cyrillic").strip().lower()

# --- AI (OpenAI-ga mos API: OpenAI / DeepSeek / OpenRouter) ---
AI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("AI_API_KEY")
AI_MODEL = os.getenv("AGENT_AI_MODEL") or os.getenv("AI_MODEL") or os.getenv("DEEPSEEK_MODEL") or "gpt-6-luna"
AI_BASE_URL = os.getenv("AI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL")

# --- Ovozli xabar (TTS) ---
TTS_ENABLED = os.getenv("AGENT_TTS_ENABLED", "true").lower() in ("1", "true", "yes")
TTS_API_KEY = os.getenv("AGENT_TTS_API_KEY") or os.getenv("OPENAI_API_KEY")
TTS_BASE_URL = os.getenv("AGENT_TTS_BASE_URL") or None
TTS_MODEL = os.getenv("AGENT_TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.getenv("AGENT_TTS_VOICE", "onyx")

# --- Saqlash ---
DB_PATH = os.getenv("AGENT_DB_PATH", str(Path(__file__).resolve().parent.parent / "post_agent.db"))
