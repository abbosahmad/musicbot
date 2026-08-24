import os
import re
import json
import asyncio
import random
from datetime import datetime, timedelta
import pytz
from loguru import logger
from openai import AsyncOpenAI
import yt_dlp
import aiohttp
import subprocess
import sys

# Test if shazamio is safe to import on this environment (e.g. Python 3.14 stability check)
HAS_SHAZAM = False
try:
    res = subprocess.run(
        [sys.executable, "-c", "import shazamio"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5
    )
    if res.returncode == 0:
        HAS_SHAZAM = True
        logger.info("Shazamio successfully verified and enabled.")
    else:
        logger.warning("Shazamio is disabled: import failed (segfault or compilation issue on this Python version).")
except Exception as e:
    logger.warning(f"Shazamio check failed: {e}. Disabling Shazam.")

import config

# --- 1. AI Integratsiyasi (DeepSeek V3) ---

def check_forbidden_keywords(artist: str, title: str) -> bool:
    """
    Check if the artist or title contains any forbidden religious or political keywords.
    Returns True if forbidden, False otherwise.
    """
    if not artist:
        artist = ""
    if not title:
        title = ""
        
    text = f"{artist} {title}".lower()
    
    # Precise list of forbidden religious and political keywords (including Uzbek cyrillic, latin, and common variants)
    religious_keywords = {
        "nashida", "nasheed", "anashid", "salovat", "solovat", "salovatlar", "salawat", 
        "islom", "islamic", "quron", "quran", "surasi", "sura", "oyat", "hadis", "hadislar", 
        "rasululloh", "payg'ambar", "mavlid", "ilohiy", "munojot", "allah", "alloh", 
        "taqvo", "ixlos", "namoz", "masjid", "makka", "duolar", "duo",
        "нашид", "ислам", "коран", "сура", "алах", "аллах", "намаз", "салават"
    }
    
    political_keywords = {
        "siyosiy", "siyosat", "prezident", "mirziyoyev", "deputat", "saylov", 
        "hukumat", "vazir", "hokim", "namoyish", "protest", "miting", "urush", 
        "harbiylar", "konstitutsiya", "saylovi", "президент", "выборы", "политика", 
        "война", "митинг", "протест", "правительство"
    }
    
    # Extract clean words for exact checking
    words = re.findall(r'[a-zA-Z0-9\'’`а-яА-ЯёЁ]+', text)
    for word in words:
        if word in religious_keywords:
            logger.warning(f"Forbidden religious keyword detected: '{word}'")
            return True
        if word in political_keywords:
            logger.warning(f"Forbidden political keyword detected: '{word}'")
            return True
            
    # Substring checks for specific phrases
    for phrase in ["juma muborak", "shavkat mirziyoyev", "shavkat mirziyoyevga", "juma muborax"]:
        if phrase in text:
            logger.warning(f"Forbidden phrase detected: '{phrase}'")
            return True
            
    return False


async def get_clean_details_with_ai(raw_artist: str, raw_title: str) -> dict:
    fallback_artist, fallback_title = extract_clean_artist_and_title(raw_artist, raw_title)
    if not fallback_artist:
        fallback_artist = _clean_single_string(raw_artist)
    if not fallback_title:
        fallback_title = _clean_single_string(raw_title)

    if not hasattr(config, 'DEEPSEEK_API_KEY') or not config.DEEPSEEK_API_KEY:
        return {
            "artist": fallback_artist or "Trend MUSIC",
            "title": fallback_title or "Musiqa",
            "is_religious": False,
            "is_political": False,
            "reason": "AI API Key missing"
        }

    try:
        raw_model_name = getattr(config, 'DEEPSEEK_MODEL', 'deepseek-v4-flash-vision-exp')
        base_url = getattr(config, 'DEEPSEEK_BASE_URL', None)
        
        if not base_url:
            if "openrouter" in raw_model_name.lower():
                base_url = "https://openrouter.ai/api/v1"
            else:
                base_url = "https://api.deepseek.com"

        model_name = raw_model_name
        if "api.deepseek.com" in base_url and model_name.startswith("deepseek/"):
            model_name = model_name.replace("deepseek/", "")

        default_headers = {}
        if "openrouter.ai" in base_url:
            default_headers = {
                "HTTP-Referer": "https://abboscoder.uz/music",
                "X-Title": "Trend Music Telegram Bot"
            }

        client = AsyncOpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=base_url,
            default_headers=default_headers if default_headers else None,
            timeout=12.0
        )

        system_prompt = """You are an expert music metadata cleaning AI for the 'Trend Musiqa' music channel.
Your task is to extract the pure, professional 'artist' (singer/performer) and 'title' (song name) from raw messy input strings.

CRITICAL ARTIST RULES:
1. Identify genuine human artists or band names (e.g., 'Shohruhxon', 'Billie Eilish', 'Eminem', 'Yulduz Usmonova', 'Doston Ergashev', 'Miyagi', 'Konsta', 'Jaloliddin Ahmadaliyev').
2. If the raw artist/title contains ANY channel name, media brand, app name, bot name, or promo text (e.g., 'Spotify', 'Spotify Muzikala', 'UzMuz', 'Taronalar', 'Dilnavo', 'Mp3lar', 'Premier', 'Rizanova', 'Kanal', 'Music', 'Media', 'Online', 'TikTok', 'Instagram', 'YouTube', etc.):
   - If a real singer exists in the text (e.g., 'Spotify - Bu Yurak - Doston Ergashev' or '@Kanal - Lola - Sevgi'), extract that real singer: artist='Doston Ergashev', title='Bu Yurak'.
   - If NO real singer is mentioned (e.g., 'Bu Yurak' or 'Брату' or 'Spotify - Bu Yurak'), set artist to 'Trend Musiqa'!
   - NEVER output 'Spotify', 'UzMuz', 'Unknown', or any other competitor channel/brand as the artist. If no real artist is known, ALWAYS use 'Trend Musiqa'.

CRITICAL TITLE & CLUTTER RULES:
3. Strip all usernames (@...), links (t.me/..., http://..., .uz, .ru, .com), hashtags (#...), and promo words ('skachat', 'yuklash', 'mp3', 'xit', 'hit', 'premyera', 'official', 'klip', 'audio').
4. PRESERVE legitimate musical tags: (Remix), (DJ ... Remix), (Speed Up), (Slowed), (Cover), (feat. ...), (ft. ...).
5. Always format in neat Title Case.

Safety Rules:
- 'is_religious': true ONLY for explicit Quran recitations, nasheeds, salovats, or sermons.
- 'is_political': true ONLY for political figure anthems, government propaganda, or warfare chants.
- Otherwise, both must be false.

Return STRICT JSON: {"artist": "Clean Artist or Trend Musiqa", "title": "Clean Title", "is_religious": false, "is_political": false, "reason": "..."}"""

        user_prompt = f"""Raw Artist: "{raw_artist}"
Raw Title: "{raw_title}" """

        create_kwargs = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1
        }
        
        # Add response_format if standard supported
        try:
            response = await client.chat.completions.create(
                **create_kwargs,
                response_format={"type": "json_object"}
            )
        except Exception:
            # Fallback without json_object constraint for models that don't support it directly
            response = await client.chat.completions.create(**create_kwargs)

        content = response.choices[0].message.content.strip()
        
        # Robust JSON parser for AI responses wrapped in ```json ```
        if "```" in content:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                content = json_match.group(1).strip()

        data = json.loads(content)
        
        # Ensure returned fields are not empty or invalid
        artist_res = (data.get("artist") or "").strip()
        title_res = (data.get("title") or "").strip()

        # Check if artist is invalid, generic, or promo
        invalid_markers = ["spotify", "unknown", "noma'lum", "nomalum", "music", "mp3", "uzmuz", "tarona", "kanal", "media", "baza", "tiktok"]
        if not artist_res or any(inv == artist_res.lower().strip() for inv in invalid_markers) or "spotify" in artist_res.lower():
            artist_res = fallback_artist or "Trend Musiqa"

        if not title_res or title_res.lower() in ["musiqa", "unknown", "track", "audio"]:
            title_res = fallback_title or "Musiqa"

        data["artist"] = artist_res
        data["title"] = title_res
            
        return data

    except Exception as e:
        err_msg = str(e).lower()
        logger.warning(f"AI xatoligi (Aqlli regex fallback ishlatiladi): {e}")
        
        if "402" in err_msg or "insufficient_quota" in err_msg or "balance" in err_msg or "401" in err_msg:
             asyncio.create_task(send_alert_to_admin(f"DeepSeek AI API xatolik berdi (Kalit/Balans): {e}. Aqlli fallback rejimida ishlamoqda."))
             
        return {
            "artist": fallback_artist or "Trend Musiqa",
            "title": fallback_title or "Musiqa",
            "is_religious": False,
            "is_political": False,
            "reason": f"AI Error: {e}"
        }

async def send_alert_to_admin(text: str):
    """
    Log kanaliga yoki adminga kutilmagan favqulodda xatoliklarni xabar qiladi.
    Circular import ni oldini olish uchun aiohttp yordamida API chaqiramiz.
    """
    try:
        if not config.ADMIN_BOT_TOKEN or not config.LOG_CHANNEL_ID: return
        url = f"https://api.telegram.org/bot{config.ADMIN_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": config.LOG_CHANNEL_ID,
            "text": f"⚠️ <b>DIQQAT - BOTDA XATOLIK:</b>\n\n{text}",
            "parse_mode": "HTML"
        }
        async with aiohttp.ClientSession() as session:
            await session.post(url, json=payload)
    except Exception as e:
        logger.error(f"Favqulodda xabar yuborishda xato: {e}")

# --- 2. YouTube API va yt-dlp (COOKIESIZ) ---

async def search_youtube_with_api(artist: str, title: str) -> dict:
    """
    YouTube Data API v3 bilan qidiruv (cookies muammosisiz)
    """
    if not hasattr(config, 'YOUTUBE_API_KEY') or not config.YOUTUBE_API_KEY:
        logger.warning("YouTube API key topilmadi")
        return None

    try:
        search_query = f"{artist} - {title} official audio"
        api_url = "https://www.googleapis.com/youtube/v3/search"

        params = {
            'part': 'snippet',
            'q': search_query,
            'type': 'video',
            'maxResults': 3,
            'key': config.YOUTUBE_API_KEY,
            'videoCategoryId': '10',
            'order': 'relevance'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if 'items' in data and data['items']:
                        for item in data['items']:
                            video_id = item['id']['videoId']
                            video_title = item['snippet']['title']
                            channel_title = item['snippet']['channelTitle']

                            logger.info(f"YouTube topildi: {video_title} - {channel_title}")

                            return {
                                'video_id': video_id,
                                'title': video_title,
                                'channel': channel_title,
                                'url': f"https://www.youtube.com/watch?v={video_id}"
                            }
                    else:
                        logger.warning("YouTube API hech narsa topmadi")
                        return None
                else:
                    logger.error(f"YouTube API xatosi: {response.status}")
                    return None

    except Exception as e:
        logger.error(f"YouTube API so'rovida xato: {e}")
        return None


def download_youtube_with_api_url(youtube_url: str) -> str:
    """
    YouTube'dan fayl yuklash (Cookies va bir nechta zamonaviy mijozlar bilan)
    """
    cookie_file = None
    for cf in ["cookies.txt", "cookies.txt.txt"]:
        if os.path.exists(cf) and os.path.getsize(cf) > 100:
            cookie_file = cf
            break

    # 1-usul: Android VR / Web Creator (zamonaviy blokirovkasiz mijozlar)
    ydl_opts_modern = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/yt_%(id)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android_vr', 'web_creator', 'ios'],
                'skip': ['dash', 'hls']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    if cookie_file:
        ydl_opts_modern['cookiefile'] = cookie_file

    # 2-usul: iOS Client
    ydl_opts_ios = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/yt_ios_%(id)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios'],
                'skip': ['dash', 'hls']
            }
        }
    }
    if cookie_file:
        ydl_opts_ios['cookiefile'] = cookie_file

    # 3-usul: Minimal / Web fallback
    ydl_opts_minimal = {
        'format': 'bestaudio[ext=mp3]/bestaudio/best',
        'outtmpl': 'downloads/yt_min_%(id)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
    }
    if cookie_file:
        ydl_opts_minimal['cookiefile'] = cookie_file

    methods = [ydl_opts_modern, ydl_opts_ios, ydl_opts_minimal]
    for i, opts in enumerate(methods, 1):
        try:
            logger.info(f"YouTube yuklash (usul {i})... (Cookies: {'Ha' if cookie_file else 'Yo`q'})")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                if info and isinstance(info, dict):
                    try:
                        filename = ydl.prepare_filename(info)
                        final_filename = os.path.splitext(filename)[0] + ".mp3"
                        if os.path.exists(final_filename) and os.path.getsize(final_filename) > 0:
                            logger.success(f"✅ YouTube'dan muvaffaqiyatli yuklandi (usul {i})!")
                            return final_filename
                    except Exception as prep_err:
                        logger.warning(f"Fayl nomini tayyorlashda ogohlantirish: {prep_err}")
                
                # Zaxira tekshirish: downloads papkasida yangi yaratilgan mp3 bormi?
                if info and isinstance(info, dict) and 'id' in info:
                    vid_id = info['id']
                    for f in os.listdir("downloads"):
                        if vid_id in f and f.endswith(".mp3"):
                            candidate = os.path.join("downloads", f)
                            if os.path.getsize(candidate) > 0:
                                logger.success(f"✅ YouTube'dan fayl topildi: {candidate}")
                                return candidate
        except Exception as e:
            logger.warning(f"YouTube usul {i} ishlamadi: {e}")
            continue

    logger.error("❌ Barcha YouTube yuklash usullari samarasiz bo'ldi")
    return None


async def get_youtube_with_api(artist: str, title: str) -> str:
    """
    YouTube API + yt-dlp kombinatsiyasi (3 usul bilan)
    """
    # 1. API bilan qidiruv
    search_result = await search_youtube_with_api(artist, title)

    if not search_result:
        logger.warning("YouTube API hech narsa topmadi")
        return None

    # 2. Topilgan URL'ni yuklash
    youtube_url = search_result['url']
    downloaded_file = await asyncio.to_thread(download_youtube_with_api_url, youtube_url)

    if downloaded_file:
        return downloaded_file

    # 3. Agar YouTube ishlamasa, boshqa qidiruv urinishi
    logger.warning("YouTube yuklash ishlamadi. Boshqa variantni sinab ko'ramiz...")

    # Boshqa qidiruv so'zi bilan
    alternative_query = f"{artist} {title} audio"
    alternative_result = await search_youtube_with_api_by_query(alternative_query)

    if alternative_result:
        alternative_url = alternative_result['url']
        alternative_file = await asyncio.to_thread(download_youtube_with_api_url, alternative_url)
        if alternative_file:
            logger.success("✅ Muqobil qidiruv bilan yuklandi!")
            return alternative_file

    logger.error("Barcha YouTube usullari ishlamadi")
    return None


async def search_youtube_with_api_by_query(query: str) -> dict:
    """
    YouTube API bilan oddiy qidiruv
    """
    if not hasattr(config, 'YOUTUBE_API_KEY') or not config.YOUTUBE_API_KEY:
        return None

    try:
        api_url = "https://www.googleapis.com/youtube/v3/search"

        params = {
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'maxResults': 1,
            'key': config.YOUTUBE_API_KEY,
            'videoCategoryId': '10',  # Music category
            'order': 'relevance'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if 'items' in data and data['items']:
                        item = data['items'][0]
                        video_id = item['id']['videoId']
                        video_title = item['snippet']['title']

                        return {
                            'video_id': video_id,
                            'title': video_title,
                            'url': f"https://www.youtube.com/watch?v={video_id}"
                        }

    except Exception as e:
        logger.error(f"Muqobil YouTube qidiruv xatosi: {e}")

    return None


async def identify_track_with_shazam(file_path: str):
    if not HAS_SHAZAM:
        return None
    try:
        from shazamio import Shazam
        shazam = Shazam()
        out = await shazam.recognize(file_path)
        track = out.get('track', {})
        if track:
            return {
                'artist': track.get('subtitle'),
                'title': track.get('title'),
                'shazam_id': track.get('key'),
                'duration': 0
            }
    except Exception as e:
        logger.warning(f"Shazam tanimadi: {e}")
    return None

# --- Yordamchi ---

def _clean_single_string(text: str) -> str:
    if not text:
        return ""

    cleaned = str(text)

    # 1. Remove telegram usernames and web URLs
    cleaned = re.sub(r'@[a-zA-Z0-9_]+', '', cleaned)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r't\.me/\S+', '', cleaned)
    cleaned = re.sub(r'www\.[a-zA-Z0-9_-]+\.[a-z]+', '', cleaned)

    # 2. Remove known channel watermarks and promotional phrases (case-insensitive)
    promo_phrases = [
        r'spotify[\_\s]*muzikala',
        r'spotify[\_\s]*music',
        r'spotify[\_\s]*uz',
        r'\bspotify\b',
        r'muzikalar[\_\s]*uzmuz',
        r'taronalar[\_\s]*qoshiqlar[\_\s]*mp3lar',
        r'taronalar[\_\s]*qoshiqlar',
        r'uzbekcha[\_\s]*muzika[\_\s]*mp3lar[\_\s]*xit(?:\s*\d+)?',
        r'qushiqlar[\_\s]*uzbekcha[\_\s]*qo[\_\'\`]?shiqllar',
        r'dilnavo[\_\s]*music',
        r'trend[\_\s]*music(?:[\_\s]*ads)?',
        r'abbostech',
        r'rizanova[\_\s]*uz',
        r'rizanova',
        r'\buzmuz\b',
        r'\btaronalar\b',
        r'\bmp3lar\b',
        r'\b(?:skachat|yuklash|yuklab\s*olish|skachat\s*mp3|mp3lar|xitlar|hitlar|premyera|taronalar)\b',
        r'\b(?:kanalimizga\s*obuna|obuna\s*bo\'ling|obuna\s*boling|kanalimiz)\b',
        r'\b(?:shazam\s*version|official\s*audio|official\s*video|rasmiy\s*kanal)\b'
    ]
    for pat in promo_phrases:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)

    # 3. Strip brackets containing ONLY promotional spam, while PRESERVING music tags
    # e.g. Preserve (Remix), (DJ ... Remix), (Speed Up), (Slowed), (Cover), (feat. ...)
    def _bracket_filter(match):
        inner = match.group(1).strip()
        inner_lower = inner.lower()
        music_markers = ['remix', 'feat', 'ft.', 'speed up', 'slowed', 'cover', 'live', 'acoustic', 'dj', 'rkt', 'perreo', 'mashup', 'suniy', 'intelakt', 'ai', 'sad', 'oriental']
        if any(m in inner_lower for m in music_markers):
            return f"({inner})"
        promo_markers = ['uzmuz', 't.me', '@', 'http', '.uz', '.ru', '.com', 'skachat', 'yuklash', 'mp3', 'tarona', 'kanal', 'baza', 'media']
        if any(p in inner_lower for p in promo_markers):
            return ""
        if len(inner) <= 15 and not any(p in inner_lower for p in promo_markers):
            return f"({inner})"
        return ""

    cleaned = re.sub(r'[\(\[\{](.*?)[\)\]\}]', _bracket_filter, cleaned)

    # 4. Remove empty brackets like (), [], {}
    cleaned = re.sub(r'[\(\[\{]\s*[\)\]\}]', '', cleaned)

    # 5. Remove standalone domain names like "site.uz", "baza.ru"
    cleaned = re.sub(r'\b[a-zA-Z0-9_-]+\.(?:uz|ru|com|net|org|io|biz|info|club|fm|tv)\b', '', cleaned, flags=re.IGNORECASE)

    # 6. Clean multiple punctuation and delimiters
    cleaned = re.sub(r'[-_\|\+•\:\.,~]+', ' ', cleaned)

    # 7. Normalize whitespace
    cleaned = ' '.join(cleaned.split()).strip()
    cleaned = re.sub(r'^[^\w\(\)]+|[^\w\(\)]+$', '', cleaned).strip()

    if len(cleaned) < 2 and not cleaned.isalnum():
        return ""

    return cleaned


def clean_title(title: str, artist: str) -> str:
    return f"{artist} - {title}"


def write_clean_metadata(file_path: str, artist: str, title: str):
    """
    MP3 fayldagi barcha eski teglarni, raqobatchi kanal logolarini to'liq tozalaydi,
    rasmiy thumbnail.jpg ni audio muqovasi (attached picture) sifatida biriktiradi 
    va yangi toza Artist va Title ni yozadi.
    """
    if not file_path or not os.path.exists(file_path):
        return

    # Spotify yoki bo'sh nomlarni Trend Musiqa ga almashtirish
    if not artist or str(artist).lower().strip() in ["spotify", "unknown artist", "unknown", "noma'lum", "nomalum"]:
        artist = "Trend Musiqa"

    thumb_path = "thumbnail.jpg"
    clean_temp = file_path.replace(".mp3", "_clean_tmp.mp3")

    # 1. FFmpeg orqali eski metadata/rasmlarni tozalash va agar thumbnail.jpg bo'lsa uni cover art qilib biriktirish
    try:
        if os.path.exists(thumb_path):
            cmd = [
                "ffmpeg", "-i", file_path, "-i", thumb_path,
                "-map", "0:a", "-map", "1:v",
                "-c:a", "copy", "-c:v", "mjpeg",
                "-id3v2_version", "3",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)",
                "-disposition:v", "attached_pic",
                "-map_metadata", "-1",
                "-y", clean_temp
            ]
        else:
            cmd = [
                "ffmpeg", "-i", file_path,
                "-map_metadata", "-1", "-vn",
                "-c:a", "copy",
                "-y", clean_temp
            ]

        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if res.returncode == 0 and os.path.exists(clean_temp) and os.path.getsize(clean_temp) > 0:
            os.replace(clean_temp, file_path)
            logger.info("✅ MP3 faylga yangi cover art FFmpeg orqali biriktirildi.")
        else:
            if os.path.exists(clean_temp):
                try: os.remove(clean_temp)
                except: pass
    except Exception as ffmpeg_err:
        logger.warning(f"FFmpeg metadata/cover yozishda xato: {ffmpeg_err}")

    # 2. Mutagen yordamida ID3 teglarni noldan tozalab, faqat toza Artist va Title yozish
    try:
        from mutagen.id3 import ID3, APIC, TIT2, TPE1
        from mutagen.mp3 import MP3

        # ID3 teglarni olish yoki yaratish
        try:
            tags = ID3(file_path)
        except Exception:
            tags = ID3()

        # Toza Artist va Title yozish
        tags.delall('TIT2')
        tags.delall('TPE1')
        tags.delall('TALB')
        tags.delall('COMM')
        tags.delall('USLT')
        tags.delall('WXXX')
        tags.delall('TXXX')
        tags.add(TPE1(encoding=3, text=[artist]))
        tags.add(TIT2(encoding=3, text=[title]))

        # Agar thumbnail.jpg bo'lsa, APIC sifatida ham yozib qo'yamiz
        if os.path.exists(thumb_path):
            try:
                tags.delall('APIC')
                with open(thumb_path, "rb") as albumart:
                    tags.add(
                        APIC(
                            encoding=3,
                            mime='image/jpeg',
                            type=3,  # Front Cover
                            desc=u'Cover',
                            data=albumart.read()
                        )
                    )
            except Exception as pic_err:
                logger.warning(f"Mutagen muqova rasmini yozishda xato: {pic_err}")

        tags.save(file_path, v2_version=3)
        logger.success(f"🎵 MP3 ID3 teglari noldan yangilandi: Artist: '{artist}', Title: '{title}'")

    except Exception as e:
        logger.error(f"⚠️ Mutagen orqali teglarni yozishda xato: {e}")


def get_daily_post_count() -> int:
    return 6  # Kuniga 6 ta musiqa


def calculate_post_times(count: int) -> list:
    if count == 0:
        return []
    tashkent_tz = pytz.timezone("Asia/Tashkent")
    now = datetime.now(tashkent_tz)
    start_time = now + timedelta(minutes=5)  # 5 daqiqa keyin boshlash

    # Har 3 soatda post (6 ta bo'lsa: 0, 3, 6, 9, 12, 15 soatlarda)
    times = [start_time + timedelta(hours=i*3) for i in range(count)]
    return times


def calculate_track_score(track: dict) -> float:
    """
    Musiqaning sifat va ommaboplik darajasini (oltin o'rtalik) aniqlash uchun ball hisoblash.
    Formula: Score = (Views + Reactions * Weight) / (AgeInHours + 2)
    """
    views = track.get('views', 0)
    reactions = track.get('reactions', 0)
    
    # 1 ta reaksiya 20 ta ko'rishga teng deb baholanadi (engagement)
    reaction_weight = 20
    engagement_score = views + (reactions * reaction_weight)
    
    # Vaqt o'tishi bilan qiymatning pasayishi (time decay)
    # Pyrogram-dan keladigan xabar vaqti UTC formatida naive datetime bo'ladi
    msg_date = track.get('date')
    if msg_date:
        age_hours = (datetime.utcnow() - msg_date).total_seconds() / 3600.0
    else:
        age_hours = 0.0
        
    age_hours = max(0.0, age_hours)
    
    # 2 soatlik bufer qo'shiladi (yangi chiqqan musiqalar cheksiz katta ball olib ketmasligi uchun)
    score = engagement_score / (age_hours + 2.0)
    return score


def clean_search_query(query: str) -> str:
    """
    Qidiruv so'rovini target botga yuborishdan oldin keraksiz belgilar, linklar va reklamalardan tozalash.
    """
    if not query:
        return ""

    invalid_artists = [
        "unknown artist", "unknown performer", "noma'lum ijrochi", "nomalum ijrochi",
        "noma'lum", "nomalum", "unknown", "trend music", "trend", "musiqa"
    ]
    for inv_art in invalid_artists:
        query = re.sub(rf'^{re.escape(inv_art)}\s*-\s*', '', query, flags=re.IGNORECASE)
        query = re.sub(rf'\s*-\s*{re.escape(inv_art)}$', '', query, flags=re.IGNORECASE)
        if query.lower().strip() == inv_art:
            query = ""

    if " - " in query:
        parts = query.split(" - ", 1)
        art, tit = extract_clean_artist_and_title(parts[0], parts[1])
        if art and art.lower().strip() not in invalid_artists:
            query = f"{art} - {tit}"
        else:
            query = tit

    # Clean promo patterns and usernames
    cleaned = _clean_single_string(query)
    cleaned = re.sub(r'\s*-\s*', ' - ', cleaned)
    cleaned = ' '.join(cleaned.split()).strip()

    return cleaned or query.strip()


def extract_clean_artist_and_title(raw_artist: str, raw_title: str, caption: str = "", filename: str = "") -> tuple:
    """
    Manba kanallardagi suv belgilari va reklamalarni tozalab, haqiqiy Artist va Qo'shiq nomini ajratib oladi.
    """
    raw_artist = (raw_artist or "").strip()
    raw_title = (raw_title or "").strip()
    caption = (caption or "").strip()
    filename = (filename or "").strip()

    promo_patterns = [
        r'muzikalar[\_\s]*uzmuz',
        r'taronalar[\_\s]*qoshiqlar[\_\s]*mp3lar',
        r'taronalar[\_\s]*qoshiqlar',
        r'uzbekcha[\_\s]*muzika[\_\s]*mp3lar[\_\s]*xit(?:\s*\d+)?',
        r'qushiqlar[\_\s]*uzbekcha[\_\s]*qo[\_\'\`]?shiqllar',
        r'dilnavo[\_\s]*music',
        r'trend[\_\s]*music(?:[\_\s]*ads)?',
        r'abbostech',
        r'rizanova[\_\s]*uz',
        r'rizanova',
        r'\buzmuz\b',
        r'\btaronalar\b',
        r'\bmp3lar\b',
        r'@[a-zA-Z0-9_]+',
        r't\.me/[a-zA-Z0-9_]+',
        r'https?://\S+',
        r'www\.[a-zA-Z0-9_-]+\.[a-z]+'
    ]

    def is_promo(text: str) -> bool:
        if not text:
            return True
        t_clean = text.lower().strip()
        if t_clean in ["unknown", "unknown artist", "unknown performer", "noma'lum", "nomalum", "trend music", "trend", "musiqa"]:
            return True
        for pat in promo_patterns:
            if re.search(pat, text, re.IGNORECASE):
                return True
        return False

    candidate_artist = raw_artist
    candidate_title = raw_title

    # Agar title fayl nomi ko'rinishida bo'lsa yoki bo'sh bo'lsa
    if not candidate_title or candidate_title.endswith('.mp3'):
        if filename:
            candidate_title = filename.replace('.mp3', '')
        elif caption:
            candidate_title = caption

    # 1. Agar raw_title ichida " - " bo'lsa (masalan: Muzikalar UzMuz - Botir Qodirov - Jim turing)
    if " - " in raw_title:
        parts = [p.strip() for p in raw_title.split(" - ") if p.strip()]
        if len(parts) >= 3:
            if is_promo(parts[0]):
                candidate_artist = parts[1]
                candidate_title = " - ".join(parts[2:])
            else:
                candidate_artist = parts[0]
                candidate_title = " - ".join(parts[1:])
        elif len(parts) == 2:
            if is_promo(candidate_artist) or is_promo(parts[0]) or not candidate_artist:
                candidate_artist = parts[0]
                candidate_title = parts[1]

    # 2. Agar artist hali ham reklama bo'lsa yoki bo'sh bo'lsa, caption dan izlash
    if (is_promo(candidate_artist) or not candidate_artist) and " - " in caption:
        parts = [p.strip() for p in caption.split(" - ") if p.strip()]
        if len(parts) >= 3 and is_promo(parts[0]):
            candidate_artist = parts[1]
            candidate_title = " - ".join(parts[2:])
        elif len(parts) >= 2:
            candidate_artist = parts[0]
            candidate_title = " - ".join(parts[1:])

    # 3. Agar artist hali ham topilmagan bo'lsa, fayl nomidan izlash
    if (is_promo(candidate_artist) or not candidate_artist) and filename:
        clean_fn = re.sub(r'^\s*muzikalar[\_\s]*uzmuz[\_\s]*', '', filename, flags=re.IGNORECASE)
        clean_fn = re.sub(r'[\_\s]*\d+\.mp3$', '.mp3', clean_fn, flags=re.IGNORECASE)
        clean_fn = clean_fn.replace('.mp3', '').replace('_', ' ')
        if " - " in clean_fn:
            parts = [p.strip() for p in clean_fn.split(" - ") if p.strip()]
            if len(parts) >= 2:
                candidate_artist = parts[0]
                candidate_title = " - ".join(parts[1:])

    # 4. Yakuniy tozalash
    clean_artist = _clean_single_string(candidate_artist)
    clean_title = _clean_single_string(candidate_title)

    # 5. Agar artist tozalangandan so'ng bo'shab qolsa va title ichida " - " qolgan bo'lsa
    if not clean_artist and " - " in clean_title:
        parts = clean_title.split(" - ", 1)
        clean_artist = parts[0].strip()
        clean_title = parts[1].strip()

    return clean_artist, clean_title


def detect_music_highlight(file_path: str, raw_text: str = "") -> str:
    """
    Musiqaning avj (highlight / drop / chorus) vaqtini aniqlaydi.
    Hech qachon '00:00' qaytarmaydi (eng kamida '00:35' yoki audioning eng baland cho'qqisini tanlaydi).
    """
    # 1. Matndan vaqtni qidirish
    if raw_text:
        time_match = re.search(r'\b([0-5]?[0-9]:[0-5][0-9])\b', raw_text)
        if time_match:
            found_time = time_match.group(1)
            parts = found_time.split(":")
            if len(parts) == 2:
                mins = int(parts[0])
                secs = int(parts[1])
                if mins > 0 or secs >= 10:
                    return f"{mins:02d}:{secs:02d}"

    # 2. Audio fayldan RMS balandlik bo'yicha tahlil qilish
    if file_path and os.path.exists(file_path):
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(file_path)
            total_duration_ms = len(audio)
            
            if total_duration_ms >= 45 * 1000:
                start_window = int(total_duration_ms * 0.15)
                end_window = int(total_duration_ms * 0.75)
                step_ms = 1000       # Har 1 soniya
                window_ms = 8000     # 8 soniyalik oyna
                
                best_time_ms = 40000 # Sukut bo'yicha 40-soniya
                max_rms = -1
                
                for t in range(start_window, max(start_window + 1000, end_window - window_ms), step_ms):
                    chunk = audio[t : t + window_ms]
                    rms = chunk.rms
                    if rms > max_rms:
                        max_rms = rms
                        best_time_ms = t
                        
                sec = int(best_time_ms / 1000)
                mins = sec // 60
                secs = sec % 60
                if mins > 0 or secs >= 10:
                    return f"{mins:02d}:{secs:02d}"
        except Exception as e:
            logger.warning(f"Avj vaqtini audio tahlilida aniqlashda xato: {e}")
            
    return "00:45"


def get_audio_duration(file_path: str) -> int:
    """
    MP3 faylning aniq davomiyligini soniyalarda hisoblaydi.
    """
    if not file_path or not os.path.exists(file_path):
        return 0
    try:
        from mutagen.mp3 import MP3
        audio = MP3(file_path)
        if audio.info and audio.info.length:
            dur = int(audio.info.length)
            if dur > 0:
                return dur
    except Exception:
        pass
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(file_path)
        dur = int(len(audio) // 1000)
        if dur > 0:
            return dur
    except Exception:
        pass
    return 0


def choose_best_result_number(text: str, query: str = "") -> str:
    """
    Qidiruv natijalarini matn ko'rinishida tahlil qilib, mos variantning tartib raqamini aniqlaydi.
    Ortiqcha jazo ballarisiz: birinchi mos tushgan yoki 1-variantni qaytaradi.
    """
    if not text:
        return "1"
        
    lines = text.split("\n")
    results = []
    
    for line in lines:
        match = re.match(r'^(\d+)[\.\)]\s*(.*)$', line.strip())
        if match:
            num = match.group(1)
            title = match.group(2).lower()
            results.append((num, title))
            
    if not results:
        return "1"
        
    # Agar qidiruv so'zi berilgan bo'lsa, moslikni tekshiramiz
    if query:
        query_words = [w.lower() for w in re.split(r'\W+', query) if len(w) > 2]
        best_num = results[0][0]
        max_matches = -1
        
        for num, title in results:
            matches = sum(1 for w in query_words if w in title)
            if matches > max_matches:
                max_matches = matches
                best_num = num
                
        if max_matches > 0:
            return best_num

    # Aks holda 1-variant
    return results[0][0]



