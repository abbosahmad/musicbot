import re
from datetime import datetime, timedelta
import pytz
import random
import config
from loguru import logger

# Tozalash uchun kalit so'zlar ro'yxati SUPER KENGAYTIRILDI
CLEANUP_KEYWORDS = [
    # Siz so'ragan so'zlar va ularning ehtimoliy ko'rinishlari
    "dilnavo music", "dil navo", "dilnavo",
    "muzikalar uzmuz", "muzika",
    "uzmuz", "uz muz",
    
    # Boshqa keng tarqalgan reklama so'zlari
    "rizanova", "nevo music", "nevomusic", "uzbek music", "xclusive",
    "mp3", "official", "telegram", "t.me", "original", "soundtrack", "live","top music", "xit", "x IT", "rek", "uzbekistan", "official video", "music video"
]

def _clean_single_string(text: str) -> str:
    """Har qanday matnni keraksiz so'zlardan universal tozalaydi."""
    if not text:
        return ""
    
    cleaned_text = text
    # Qavs va skobkalarni ichidagi matn bilan birga olib tashlash
    cleaned_text = re.sub(r'[\(\[\{].*?[\)\]\}]', '', cleaned_text)
    # Domen nomlari va @username larni olib tashlash
    cleaned_text = re.sub(r'[\w\.-]+(\.uz|\.com|\.ru|\.net)\b', '', cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r'@[a-zA-Z0-9_]+', '', cleaned_text)

    # Maxsus ro'yxatdagi kalit so'zlarni olib tashlash (turli yozilishlarni hisobga olgan holda)
    for keyword in CLEANUP_KEYWORDS:
        # Bu qator "uz muz" so'zini "uzmuz" yoki "uz.muz" ko'rinishida ham topa oladi
        pattern = r'\b' + r'[\s\.\-_]*'.join(map(re.escape, keyword.split())) + r'\b'
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)

    # Ortiqcha tinish belgilarini bo'shliqqa almashtirish
    cleaned_text = re.sub(r'[^\w\s-]', ' ', cleaned_text) # Chiziqchani saqlab qolamiz
    # Ortiqcha bo'shliqlarni tozalash
    cleaned_text = ' '.join(cleaned_text.split()).strip()
    
    return cleaned_text

def _parse_artist_and_title(artist_str: str, title_str: str) -> tuple:
    """
    Musiqaning ijrochisi va nomini iloji boricha aniq topishga harakat qiladi.
    """
    if artist_str and 'unknown' not in artist_str.lower() and len(artist_str) > 2:
        return artist_str, title_str

    separators = [' - ', ' – ', ' -- ', ' — ', '-']
    text_to_parse = title_str or ""
    
    for sep in separators:
        if sep in text_to_parse:
            parts = text_to_parse.split(sep, 1)
            if len(parts) == 2 and len(parts[0]) < 50 and len(parts[1]) < 100:
                return parts[0], parts[1]

    return "", text_to_parse


def clean_title(title: str, artist: str) -> str:
    """
    Ijrochi va sarlavhani aqlli tahlil qiladi, tozalaydi va yakuniy formatga keltiradi.
    """
    parsed_artist, parsed_title = _parse_artist_and_title(artist, title)

    cleaned_artist = _clean_single_string(parsed_artist)
    cleaned_title = _clean_single_string(parsed_title)

    if cleaned_artist:
        cleaned_title = re.sub(re.escape(cleaned_artist), '', cleaned_title, flags=re.IGNORECASE).strip(" -")
        final_title = cleaned_title if cleaned_title else _clean_single_string(title)
        return f"🎧 {cleaned_artist.strip()} – {final_title.capitalize()}"
    else:
        final_title = cleaned_title if cleaned_title else _clean_single_string(title)
        return f"🎧 {final_title.capitalize()}"

def calculate_post_times(count: int) -> list:
    if count == 0: return []
    tashkent_tz = pytz.timezone("Asia/Tashkent")
    now = datetime.now(tashkent_tz)
    start_time = now + timedelta(minutes=15)
    if start_time.hour < config.PLANNING_HOUR:
        start_time = start_time.replace(hour=config.PLANNING_HOUR, minute=0)
    end_time = now.replace(hour=23, minute=30, second=0, microsecond=0)
    if start_time >= end_time:
        return [now + timedelta(minutes=i*10) for i in range(1, count + 1)]
    total_seconds = (end_time - start_time).total_seconds()
    interval = total_seconds / count if count > 0 else 0
    times = [start_time + timedelta(seconds=interval * i) for i in range(count)]
    return sorted(times)

def get_daily_post_count() -> int:
    tashkent_tz = pytz.timezone("Asia/Tashkent")
    today = datetime.now(tashkent_tz).day
    if today % 2 == 0:
        logger.info(f"Bugun sana juft ({today}), reja bo'yicha 2 ta post yuboriladi.")
        return 2
    else:
        logger.info(f"Bugun sana toq ({today}), reja bo'yicha 3 ta post yuboriladi.")
        return 3