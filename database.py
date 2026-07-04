# database.py
import os
import re
import asyncpg
from loguru import logger
from typing import Set, Dict, Any, List
from dotenv import load_dotenv
from pathlib import Path

# Load env variables if not loaded
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is required. Please set it in .env file.")
db_pool = None
posted_track_ids: Set[str] = set()
posted_track_hashes: Set[str] = set()

# Matnlarni o'xshashlikka tekshirish uchun normallashtirish
def normalize_string(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    # Qavslar ichidagi yozuvlarni olib tashlash (masalan: [Remix], (Official video))
    text = re.sub(r'[\(\[\{].*?[\)\]\}]', '', text)
    # Qo'shiqlar uchun keng tarqalgan so'zlarni tozalash
    text = re.sub(r'\b(remix|cover|slowed|reverb|speed up|lyrics|official|audio|video|clip|mp3|t\.me\S*|hq|muz|trend)\b', '', text)
    # Faqat harflar va raqamlarni qoldirish
    text = re.sub(r'[^a-z0-9]', '', text)
    return text.strip()

# Standart sozlamalar
DEFAULT_SETTINGS = {
    "planning_hour": "5",       # Rejalashtirish soati (0-23)
    "daily_post_count": "5",    # Kunlik postlar soni
    "source_channels": "@Muzikalar_UzMuz, @Taronalar_qoshiqlar_mp3lar", # Vergul bilan ajratilgan manba kanallar
    "demo_duration": "30",      # Demo davomiyligi (sekund)
    "night_mode": "false",      # Tun rejimi (true/false)
    "night_start": "23",        # Tun boshlanishi
    "night_end": "7",            # Tun tugashi (tong)
    "target_search_bot": "@Zoryuklabot" # Qidiruv boti nomi
}

async def setup_database():
    global db_pool, posted_track_ids, posted_track_hashes
    try:
        # Mask the password in DATABASE_URL for security logging
        masked_url = DATABASE_URL
        if "@" in DATABASE_URL:
            try:
                parts = DATABASE_URL.split("@", 1)
                prefix = parts[0]
                suffix = parts[1]
                if ":" in prefix:
                    subparts = prefix.split(":", 2)
                    scheme = subparts[0]
                    user = subparts[1].replace("//", "")
                    masked_url = f"{scheme}//{user}:*****@{suffix}"
            except Exception:
                masked_url = "postgresql://*****"
        logger.info(f"PostgreSQL ulanishi o'rnatilmoqda: {masked_url}")
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        
        async with db_pool.acquire() as conn:
            # 1. Posted Tracks Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS posted_tracks (
                    id SERIAL PRIMARY KEY,
                    track_id VARCHAR(255) NOT NULL UNIQUE,
                    artist VARCHAR(255),
                    title VARCHAR(255),
                    post_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 2. Settings Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key VARCHAR(255) PRIMARY KEY,
                    value TEXT
                )
            """)

            # 3. Daily Schedule Jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_schedule (
                    id SERIAL PRIMARY KEY,
                    post_time TIMESTAMP WITH TIME ZONE NOT NULL,
                    track_id VARCHAR(255) NOT NULL,
                    artist VARCHAR(255),
                    title VARCHAR(255),
                    chat_id BIGINT,
                    message_id BIGINT,
                    direct_file_path VARCHAR(512),
                    is_posted BOOLEAN DEFAULT FALSE
                )
            """)
            
            # Standart sozlamalarni tekshirish va qo'shish
            for key, value in DEFAULT_SETTINGS.items():
                await conn.execute("""
                    INSERT INTO bot_settings (key, value) 
                    VALUES ($1, $2)
                    ON CONFLICT (key) DO NOTHING
                """, key, value)
            
            # Xotiraga posted_tracks ni yuklash
            rows = await conn.fetch("SELECT track_id, artist, title FROM posted_tracks")
            posted_track_ids = {row['track_id'] for row in rows}
            posted_track_hashes = {normalize_string(f"{row['artist']} {row['title']}") for row in rows if row['artist'] or row['title']}
            
        logger.success(f"Ma'lumotlar bazasi PostgreSQL sozlandi. {len(posted_track_ids)} ta trek xotirada, {len(posted_track_hashes)} ta unikal nomlar keshda.")
        
    except Exception as e:
        logger.error(f"PostgreSQL bazasini sozlashda xatolik: {e}")
        raise e

async def is_track_posted(track_id: str) -> bool:
    return str(track_id) in posted_track_ids

async def is_similar_track_posted(artist: str, title: str) -> bool:
    norm_candidate = normalize_string(f"{artist} {title}")
    if not norm_candidate:
        return False
    
    # 1. Tezkor aniq moslikni tekshirish
    if norm_candidate in posted_track_hashes:
        return True
        
    # 2. Noaniq (Fuzzy) qidiruv - imlo xatolari va kichik farqlarni aniqlash (85% o'xshashlik)
    from difflib import SequenceMatcher
    for posted_norm in posted_track_hashes:
        # Matematik filtr: agar uzunliklar farqi 15% dan ko'p bo'lsa, o'xshashlik 85% dan past bo'ladi
        max_len = max(len(norm_candidate), len(posted_norm))
        if max_len > 0 and abs(len(norm_candidate) - len(posted_norm)) > max_len * 0.15:
            continue
            
        ratio = SequenceMatcher(None, norm_candidate, posted_norm).ratio()
        if ratio >= 0.85:
            logger.info(f"⚠️ O'xshash musiqa aniqlandi (O'xshashlik: {ratio*100:.1f}%): '{artist} - {title}'")
            return True
            
    return False

async def add_track_to_db(track_id: str, artist: str, title: str):
    global db_pool, posted_track_ids, posted_track_hashes
    if str(track_id) in posted_track_ids:
        return

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO posted_tracks (track_id, artist, title) VALUES ($1, $2, $3) ON CONFLICT (track_id) DO NOTHING",
                str(track_id), artist, title
            )
        posted_track_ids.add(str(track_id))
        norm = normalize_string(f"{artist} {title}")
        if norm:
            posted_track_hashes.add(norm)
        logger.info(f"Yangi trek bazaga qo'shildi: {track_id} | {artist} - {title}")
    except Exception as e:
        logger.error(f"Trekni bazaga qo'shishda xatolik: {e}")

async def get_setting(key: str, default=None) -> str:
    global db_pool
    if not db_pool:
        return default or DEFAULT_SETTINGS.get(key, "")
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM bot_settings WHERE key = $1", key)
            return row['value'] if row else (default or DEFAULT_SETTINGS.get(key, ""))
    except Exception as e:
        logger.error(f"Sozlamani olishda xato ({key}): {e}")
        return default

async def set_setting(key: str, value: str):
    global db_pool
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO bot_settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                key, str(value)
            )
        logger.info(f"Sozlama yangilandi: {key} = {value}")
    except Exception as e:
        logger.error(f"Sozlamani saqlashda xato ({key}): {e}")

async def get_all_settings() -> Dict[str, Any]:
    global db_pool
    if not db_pool:
        return {}
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value FROM bot_settings")
            return {row['key']: row['value'] for row in rows}
    except Exception as e:
        logger.error(f"Barcha sozlamalarni olishda xato: {e}")
        return {}

# --- Daily Schedule helper functions ---
async def save_daily_schedule(schedule_entries: List[Dict[str, Any]]):
    global db_pool
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            # Clear previous unposted schedule entries to prevent duplicate items
            await conn.execute("DELETE FROM daily_schedule WHERE is_posted = FALSE")
            for entry in schedule_entries:
                await conn.execute("""
                    INSERT INTO daily_schedule (post_time, track_id, artist, title, chat_id, message_id, direct_file_path, is_posted)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, entry['post_time'], entry['track_id'], entry['artist'], entry['title'],
                     entry.get('chat_id'), entry.get('message_id'), entry.get('direct_file_path'), entry.get('is_posted', False))
        logger.info(f"✅ Daily schedule saved to database ({len(schedule_entries)} entries).")
    except Exception as e:
        logger.error(f"Error saving daily schedule: {e}")

async def get_active_schedule() -> List[Dict[str, Any]]:
    global db_pool
    if not db_pool:
        return []
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT post_time, track_id, artist, title, chat_id, message_id, direct_file_path, is_posted
                FROM daily_schedule 
                WHERE post_time >= NOW() - INTERVAL '15 minutes' AND is_posted = FALSE
                ORDER BY post_time ASC
            """)
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting active schedule: {e}")
        return []

async def mark_schedule_posted(track_id: str):
    global db_pool
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE daily_schedule SET is_posted = TRUE WHERE track_id = $1", str(track_id))
        logger.info(f"Schedule entry marked as posted for track_id: {track_id}")
    except Exception as e:
        logger.error(f"Error marking schedule posted: {e}")

async def update_schedule_entry(post_time, track_id: str, artist: str, title: str, direct_file_path: str):
    global db_pool
    if not db_pool:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE daily_schedule 
                SET track_id = $1, artist = $2, title = $3, direct_file_path = $4
                WHERE post_time = $5 AND is_posted = FALSE
            """, str(track_id), artist, title, direct_file_path, post_time)
        logger.info(f"Schedule entry updated in DB for post_time {post_time}")
    except Exception as e:
        logger.error(f"Error updating schedule entry: {e}")
