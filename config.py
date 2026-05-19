import os
from dotenv import load_dotenv
from pathlib import Path

# .env faylidan o'zgaruvchilarni yuklash
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# --- Asosiy Telegram Sozlamalari ---
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN") or "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 123456789))

# --- AI Sozlamalari (DeepSeek) ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# --- YouTube API ---
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# --- Kanallar Sozlamalari ---
# Agar .env da bo'lmasa 0 qaytaradi, bu xatolikni oldini oladi lekin tekshirish kerak bo'lishi mumkin
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 0))
MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID", 0))
BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", 0))

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