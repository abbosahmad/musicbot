# database.py

import sqlite3
from loguru import logger
from typing import Set

DB_NAME = "posted_tracks.db"
db_connection = None
db_cursor = None
posted_track_ids: Set[str] = set()

async def setup_database():
    global db_connection, db_cursor, posted_track_ids
    try:
        db_connection = sqlite3.connect(DB_NAME)
        db_cursor = db_connection.cursor()
        
        db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS posted_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id TEXT NOT NULL UNIQUE,
                artist TEXT,
                title TEXT,
                post_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db_connection.commit()
        
        db_cursor.execute("SELECT track_id FROM posted_tracks")
        rows = db_cursor.fetchall()
        posted_track_ids = {row[0] for row in rows}
        
        logger.success(f"Ma'lumotlar bazasi sozlandi. Xotiraga {len(posted_track_ids)} ta trek ID si yuklandi.")
        
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
        logger.warning(f"Trek {track_id} bazaga qo'shish vaqtida allaqachon mavjud edi.")
    except Exception as e:
        logger.error(f"Trekni bazaga qo'shishda xatolik: {e}")