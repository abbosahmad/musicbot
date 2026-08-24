import os
from dotenv import load_dotenv
from pathlib import Path

# .env faylidan o'zgaruvchilarni yuklash
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# --- Asosiy Telegram Sozlamalari ---
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
if not ADMIN_BOT_TOKEN:
    raise ValueError("ADMIN_BOT_TOKEN is required. Please set it in .env file.")
_admin_user_id = os.getenv("ADMIN_USER_ID")
if not _admin_user_id:
    raise ValueError("ADMIN_USER_ID is required. Please set it in .env file.")
ADMIN_USER_ID = int(_admin_user_id)

# --- AI Sozlamalari (DeepSeek / OpenRouter) ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-v4-flash-vision-exp")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL")

# --- YouTube API ---
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# --- Kanallar Sozlamalari ---
# Agar .env da bo'lmasa 0 qaytaradi, bu xatolikni oldini oladi lekin tekshirish kerak bo'lishi mumkin
def _parse_channel_id(val):
    if not val:
        return 0
    try:
        return int(val)
    except ValueError:
        return val.strip()

LOG_CHANNEL_ID = _parse_channel_id(os.getenv("LOG_CHANNEL_ID", "0"))
MAIN_CHANNEL_ID = _parse_channel_id(os.getenv("MAIN_CHANNEL_ID", "0"))
BACKUP_CHANNEL_ID = _parse_channel_id(os.getenv("BACKUP_CHANNEL_ID", "0"))

MAIN_CHANNEL_LINK = "https://t.me/trend_musiqaUZ"
MAIN_CHANNEL_NAME = "Trend MUSIC🔥❤️"

# --- Userbot Sozlamalari ---
USERBOT_API_ID = int(os.getenv("USERBOT_API_ID", 0))
USERBOT_API_HASH = os.getenv("USERBOT_API_HASH")
USERBOT_SESSION_STRING = os.getenv("USERBOT_SESSION_STRING")

# --- Manba Kanallar ---
SOURCE_CHANNELS = [
    '@Muzikalar_UzMuz',
]

# --- Qora Ro'yxat (Bloklash uchun) ---
BLACKLIST_CHANNELS = [
    # 'AliMuzTv', 'Surxon_Muz', 'Uzmuz' # Hozircha o'chirilgan
]
BLACKLIST_KEYWORDS = [
    # '@AliMuzTv', '@Surxon_Muz', 'AliMuz', 'Surxon Muz' # Hozircha o'chirilgan
]

# --- Botning Ishlash Mantig'i ---
PLANNING_HOUR = 8
DEMO_DURATION_SECONDS = 30