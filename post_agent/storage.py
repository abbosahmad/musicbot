from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiosqlite

# Telegram media turi -> post toifasi
KIND_CATEGORY = {
    "video": "clip",
    "animation": "clip",
    "video_note": "clip",
    "voice": "voice",
    "audio": "music",
}

CATEGORY_LABELS = {
    "quote": "💡 Aqlli gap",
    "clip": "🎬 Kino parcha",
    "voice": "🎙 Ovozli xabar",
    "music": "🎵 Musiqa",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    category TEXT NOT NULL,
    file_id TEXT NOT NULL,
    file_unique_id TEXT UNIQUE NOT NULL,
    title TEXT DEFAULT '',
    note TEXT DEFAULT '',
    used_count INTEGER DEFAULT 0,
    last_used_at TEXT,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    text TEXT DEFAULT '',
    media_id INTEGER,
    message_id INTEGER,
    created_at TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, path: str):
        self.path = path
        self.db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(_SCHEMA)
        await self.db.commit()

    async def close(self):
        if self.db:
            await self.db.close()

    async def add_media(self, kind: str, file_id: str, file_unique_id: str,
                        title: str = "", note: str = "") -> Optional[int]:
        """Kutubxonaga media qo'shadi. Takror bo'lsa None qaytaradi."""
        cur = await self.db.execute(
            "INSERT OR IGNORE INTO media (kind, category, file_id, file_unique_id, title, note, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, KIND_CATEGORY[kind], file_id, file_unique_id, title or "", note or "",
             datetime.now(timezone.utc).isoformat()),
        )
        await self.db.commit()
        return cur.lastrowid if cur.rowcount else None

    async def delete_media(self, media_id: int) -> bool:
        cur = await self.db.execute("DELETE FROM media WHERE id = ?", (media_id,))
        await self.db.commit()
        return cur.rowcount > 0

    async def get_media(self, media_id: int) -> Optional[Dict]:
        async with self.db.execute("SELECT * FROM media WHERE id = ?", (media_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def pick_media(self, category: str) -> Optional[Dict]:
        """Eng kam ishlatilgan mediani tanlaydi (teng bo'lsa tasodifiy)."""
        async with self.db.execute(
            "SELECT * FROM media WHERE category = ? ORDER BY used_count ASC, RANDOM() LIMIT 1",
            (category,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def mark_used(self, media_id: int):
        await self.db.execute(
            "UPDATE media SET used_count = used_count + 1, last_used_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), media_id),
        )
        await self.db.commit()

    async def count_by_category(self) -> Dict[str, Dict[str, int]]:
        """{'clip': {'total': 5, 'unused': 2}, ...}"""
        result = {}
        async with self.db.execute(
            "SELECT category, COUNT(*) AS total, SUM(CASE WHEN used_count = 0 THEN 1 ELSE 0 END) AS unused "
            "FROM media GROUP BY category"
        ) as cur:
            async for row in cur:
                result[row["category"]] = {"total": row["total"], "unused": row["unused"] or 0}
        return result

    async def add_post(self, category: str, text: str, media_id: Optional[int], message_id: Optional[int]):
        await self.db.execute(
            "INSERT INTO posts (category, text, media_id, message_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (category, text or "", media_id, message_id, datetime.now(timezone.utc).isoformat()),
        )
        await self.db.commit()

    async def recent_texts(self, limit: int = 15) -> List[str]:
        """Takrorlanmaslik uchun AI ga beriladigan oxirgi matnlar."""
        async with self.db.execute(
            "SELECT text FROM posts WHERE text != '' ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            return [row["text"] async for row in cur]

    async def last_category(self) -> Optional[str]:
        async with self.db.execute("SELECT category FROM posts ORDER BY id DESC LIMIT 1") as cur:
            row = await cur.fetchone()
        return row["category"] if row else None

    async def post_count(self) -> int:
        async with self.db.execute("SELECT COUNT(*) AS c FROM posts") as cur:
            row = await cur.fetchone()
        return row["c"]
