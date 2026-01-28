# database.py

import sqlite3
from loguru import logger
from typing import Set, Dict, Any

DB_NAME = "posted_tracks.db"
db_connection = None
db_cursor = None
posted_track_ids: Set[str] = set()

# Standart sozlamalar
DEFAULT_SETTINGS = {
    "planning_hour": "5",       # Rejalashtirish soati (0-23)
    "daily_post_count": "5",    # Kunlik postlar soni
    "source_channels": "@Muzikalar_UzMuz", # Vergul bilan ajratilgan
    "demo_duration": "30",      # Demo davomiyligi (sekund)
    "night_mode": "false",      # Tun rejimi (true/false)
    "night_start": "23",        # Tun boshlanishi
    "night_end": "7"            # Tun tugashi (tong)
}

async def setup_database():
    global db_connection, db_cursor, posted_track_ids
    try:
        db_connection = sqlite3.connect(DB_NAME, check_same_thread=False)
        db_cursor = db_connection.cursor()
        
        # 1. Posted Tracks Jadvali
        db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS posted_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id TEXT NOT NULL UNIQUE,
                artist TEXT,
                title TEXT,
                post_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Settings Jadvali
        db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Standart sozlamalarni tekshirish va qo'shish
        for key, value in DEFAULT_SETTINGS.items():
            db_cursor.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
            
        db_connection.commit()
        
        # Xotiraga posted_tracks ni yuklash
        db_cursor.execute("SELECT track_id FROM posted_tracks")
        rows = db_cursor.fetchall()
        posted_track_ids = {row[0] for row in rows}
        
        logger.success(f"Ma'lumotlar bazasi sozlandi. {len(posted_track_ids)} ta trek xotirada.")
        
    except Exception as e:
        logger.error(f"Ma'lumotlar bazasini sozlashda xatolik: {e}")

async def is_track_posted(track_id: str) -> bool:
    return track_id in posted_track_ids

async def add_track_to_db(track_id: str, artist: str, title: str):
    global db_connection, db_cursor
    if track_id in posted_track_ids:
        return

    try:
        db_cursor.execute(
            "INSERT INTO posted_tracks (track_id, artist, title) VALUES (?, ?, ?)",
            (str(track_id), artist, title)
        )
        db_connection.commit()
        posted_track_ids.add(str(track_id))
        logger.info(f"Yangi trek bazaga qo'shildi: {track_id} | {artist} - {title}")
    except sqlite3.IntegrityError:
        pass
    except Exception as e:
        logger.error(f"Trekni bazaga qo'shishda xatolik: {e}")

# --- SOZLAMALAR BILAN ISHLASH ---

def get_setting(key: str, default=None) -> str:
    global db_cursor
    try:
        db_cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
        result = db_cursor.fetchone()
        return result[0] if result else (default or DEFAULT_SETTINGS.get(key, ""))
    except Exception as e:
        logger.error(f"Sozlamani olishda xato ({key}): {e}")
        return default

def set_setting(key: str, value: str):
    global db_connection, db_cursor
    try:
        db_cursor.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, str(value)))
        db_connection.commit()
        logger.info(f"Sozlama yangilandi: {key} = {value}")
    except Exception as e:
        logger.error(f"Sozlamani saqlashda xato ({key}): {e}")

def get_all_settings() -> Dict[str, Any]:
    global db_cursor
    try:
        db_cursor.execute("SELECT key, value FROM bot_settings")
        return dict(db_cursor.fetchall())
    except Exception as e:
        logger.error(f"Barcha sozlamalarni olishda xato: {e}")
        return {}
