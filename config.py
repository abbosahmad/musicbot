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

MAIN_CHANNEL_LINK = os.getenv("MAIN_CHANNEL_LINK", "https://t.me/trend_musiqauz")
MAIN_CHANNEL_NAME = os.getenv("MAIN_CHANNEL_NAME", "Trend Music")
CUSTOM_EMOJI_ID = os.getenv("CUSTOM_EMOJI_ID", "5222472119295684375")

# --- Userbot Sozlamalari ---
USERBOT_API_ID = int(os.getenv("USERBOT_API_ID", 0))
USERBOT_API_HASH = os.getenv("USERBOT_API_HASH")
USERBOT_SESSION_STRING = os.getenv("USERBOT_SESSION_STRING")

# --- Manba Kanallar (2 xil toifa) ---
# 1. Bot orqali yangilanadigan kanallar (Zoryuklabot orqali toza varianti qidiriladi)
CLEAN_SOURCE_CHANNELS = [
    '@Muzikalar_UzMuz',
]

# 2. To'g'ridan-to'g'ri moslanadigan kanallar (Zoryuklabot ga yuborilmaydi, kanaldan to'g'ridan-to'g'ri moslab joylanadi)
DIRECT_SOURCE_CHANNELS = [
    '@Taronalar_qoshiqlar_mp3lar',
]

# Umumiy ro'yxat (userbot a'zo bo'lishi uchun)
SOURCE_CHANNELS = list(set(CLEAN_SOURCE_CHANNELS + DIRECT_SOURCE_CHANNELS))

# --- Qora Ro'yxat (Bloklash uchun) ---
BLACKLIST_CHANNELS = [
    # 'AliMuzTv', 'Surxon_Muz', 'Uzmuz'
]
BLACKLIST_KEYWORDS = [
    # '@AliMuzTv', '@Surxon_Muz', 'AliMuz', 'Surxon Muz'
]

# --- Botning Ishlash Mantig'i ---
PLANNING_HOUR = 8