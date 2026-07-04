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
    if not hasattr(config, 'DEEPSEEK_API_KEY') or not config.DEEPSEEK_API_KEY:
        return {
            "artist": _clean_single_string(raw_artist),
            "title": _clean_single_string(raw_title),
            "is_religious": False,
            "is_political": False,
            "reason": "AI API Key missing"
        }

    try:
        client = AsyncOpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )

        system_prompt = """You are a music metadata cleaning and safety evaluation expert.
Your task is to extract the clean 'artist' and 'title' from raw input, and evaluate if the track contains religious or political content.
- Clean the artist and title: Remove ads, channel names (@...), website URLs, and promotional keywords. If the artist is purely promotional, set it to "". Fix capitalization (Title Case).
- Evaluate content (Be very lenient and conservative when flagging):
  1. Set 'is_religious' to true ONLY if the track is explicitly a direct Islamic prayer, Quran recitation, nasheed, salovat, or religious chant. Do NOT flag general cultural love/life songs that mention religious terms or God in a general metaphorical or cultural way.
  2. Set 'is_political' to true ONLY if the track is explicitly about political figures (e.g. presidents, ministers), governments, elections, military/war propaganda, or political protests. Do NOT flag general songs about struggle, prison, history, life, or freedom unless they are clearly political propaganda or direct government commentary.
  3. Otherwise, set both to false.
  4. Write a brief explanation for your safety evaluation in 'reason'.
- Return ONLY a JSON object: {"artist": "...", "title": "...", "is_religious": true/false, "is_political": true/false, "reason": "..."}"""

        user_prompt = f"""Raw Artist: "{raw_artist}"
Raw Title: "{raw_title}" """

        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={ "type": "json_object" },
            temperature=0.1
        )

        content = response.choices[0].message.content
        data = json.loads(content)
        return data

    except Exception as e:
        err_msg = str(e).lower()
        logger.error(f"AI xatoligi (Fallback ishlatiladi): {e}")
        
        # DeepSeek balansi tugasa (402 balance xatosi kabi) yoki katta xatolik bo'lsa
        if "402" in err_msg or "insufficient_quota" in err_msg or "balance" in err_msg:
             asyncio.create_task(send_alert_to_admin(f"DeepSeek AI API xatolik berdi yoki balansi tugadi! Fallback rejimga o'tildi.\n\nXato: {e}"))
             
        return {
            "artist": _clean_single_string(raw_artist),
            "title": _clean_single_string(raw_title),
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
    YouTube'dan fayl yuklash (COOKIESIZ - 3 ta usul)
    """
    # 1-usul: Android client (cookies'siz)
    ydl_opts_android = {
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
                'player_client': ['android'],
                'skip': ['dash', 'hls', 'native']
            }
        },
        'http_headers': {
            'User-Agent': 'com.google.android.youtube/18.33.35 (Linux; U; Android 11) gzip'
        },
        'sleep_interval': 1,
    }

    # 2-usul: Web client
    ydl_opts_web = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/yt_web_%(id)s.%(ext)s',
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
                'player_client': ['web'],
                'skip': ['dash', 'hls']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        },
        'sleep_interval': 2,
    }

    # 3-usul: Minimal (eng ishonchli)
    ydl_opts_minimal = {
        'format': 'bestaudio[ext=mp3]/bestaudio/best',
        'outtmpl': 'downloads/yt_min_%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
    }

    for i, opts in enumerate([ydl_opts_android, ydl_opts_web, ydl_opts_minimal], 1):
        try:
            logger.info(f"YouTube yuklash (usul {i})...")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                if info:
                    filename = ydl.prepare_filename(info)
                    final_filename = os.path.splitext(filename)[0] + ".mp3"

                    if os.path.exists(final_filename):
                        logger.success(f"✅ YouTube'dan muvaffaqiyatli yuklandi (usul {i})!")
                        return final_filename
        except Exception as e:
            logger.warning(f"Usul {i} ishlamadi: {e}")
            continue

    logger.error("❌ Barcha YouTube usullari ishlamadi")
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
    # Remove brackets content e.g. [Muzikalar_UzMuz] or (UzMuz)
    cleaned_text = re.sub(r'[\(\[\{].*?[\)\]\}]', '', text)
    # Remove usernames
    cleaned_text = re.sub(r'@[a-zA-Z0-9_]+', '', cleaned_text)
    # Remove URLs/websites
    cleaned_text = re.sub(r'(https?://)?(www\.)?[a-zA-Z0-9-]+\.[a-z]{2,}(/[a-zA-Z0-9_-]*)*', '', cleaned_text)
    
    # Split into words and check each word individually
    words = cleaned_text.split()
    clean_words = []
    
    # Substrings to search for and remove inside words (e.g. UzMuz, MuzMusic, ZoryuklaBot)
    promo_substrings = [
        "muz", "mp3", "rap", "bot", "tv", "fm", "sound", "music", "audio", "track", 
        "tarona", "xit", "hit", "baza", "bass", "skachat", "yuklash", "status", 
        "klip", "media", "premyera", "yangi", "shou", "show", "rizanova", 
        "uzbekona", "taronalar", "xitlar", "hitlar"
    ]
    
    # Exact promotional words (case-insensitive matches)
    promo_exact = {
        "uz", "ru", "net", "com", "org", "info", "portal", "t.me", "telegram", 
        "kanal", "channel", "group", "official", "original", "remix", "remiks", 
        "shazam", "klub", "club", "uzb", "uzbek"
    }
    
    for word in words:
        # Strip punctuation from word boundaries for comparison
        clean_word = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$', '', word).lower()
        if not clean_word:
            continue
            
        # Check if it matches promo exact or contains any promo substrings
        is_promo = False
        if clean_word in promo_exact:
            is_promo = True
        else:
            for sub in promo_substrings:
                if sub in clean_word:
                    is_promo = True
                    break
                    
        if not is_promo:
            clean_words.append(word)
            
    # Join and clean up punctuation
    cleaned_text = ' '.join(clean_words)
    cleaned_text = re.sub(r'[-_\|\+•\:\.,~]+', ' ', cleaned_text)
    
    # Clean multiple spaces
    cleaned_text = ' '.join(cleaned_text.split()).strip()
    
    # If the clean text contains nothing but punctuation or is too short
    if len(cleaned_text) < 2 and not cleaned_text.isalnum():
        return ""
        
    return cleaned_text


def clean_title(title: str, artist: str) -> str:
    return f"{artist} - {title}"


def write_clean_metadata(file_path: str, artist: str, title: str):
    """
    Writes the clean artist and title into the MP3's ID3 tags using mutagen.
    Removes any old competitor images/comments and embeds the channel's custom thumbnail.jpg into the MP3 file.
    """
    # 1. Reconstruct MP3 container using FFmpeg to fix header errors and strip old cover art (-vn)
    clean_temp = file_path.replace(".mp3", "_clean_tmp.mp3")
    try:
        res = subprocess.run(
            ["ffmpeg", "-i", file_path, "-map_metadata", "-1", "-vn", "-c:a", "copy", "-y", clean_temp],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10
        )
        if res.returncode == 0 and os.path.exists(clean_temp) and os.path.getsize(clean_temp) > 0:
            os.replace(clean_temp, file_path)
            logger.info("✅ MP3 fayl konteyneri FFmpeg orqali muvaffaqiyatli tiklandi.")
        else:
            if os.path.exists(clean_temp):
                os.remove(clean_temp)
    except Exception as ffmpeg_err:
        logger.warning(f"FFmpeg orqali MP3 ni tiklashda xato: {ffmpeg_err}")

    # 2. Write metadata and embed custom cover art using Mutagen
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC
        
        def apply_tags(path):
            try:
                audio = EasyID3(path)
            except Exception:
                audio = MP3(path)
                audio.add_tags()
                audio = EasyID3(path)
                
            # Clean all other tags to remove competitor promo
            for key in list(audio.keys()):
                del audio[key]
                
            audio['artist'] = artist
            audio['title'] = title
            audio.save()

            # Remove old embedded APIC pictures and embed custom channel thumbnail.jpg
            try:
                tags = ID3(path)
                tags.delall('APIC')
                
                thumb_path = "thumbnail.jpg"
                if os.path.exists(thumb_path):
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
                tags.save()
            except Exception as pic_err:
                logger.warning(f"Album art muqova rasmini yozishda xato: {pic_err}")

        try:
            apply_tags(file_path)
            logger.success(f"🎵 MP3 ID3 teglari va muqova rasmi yangilandi: Artist: '{artist}', Title: '{title}'")
        except Exception as mutagen_err:
            logger.warning(f"⚠️ Mutagen teglarni yozishda xatolik berdi: {mutagen_err}. FFmpeg orqali qayta kodlash (re-encode) bajarilmoqda...")
            
            # Fallback: re-encode the file using FFmpeg to rebuild the audio frame sync (-vn strips video/pictures)
            clean_temp2 = file_path.replace(".mp3", "_reencode_tmp.mp3")
            res_encode = subprocess.run(
                ["ffmpeg", "-i", file_path, "-map_metadata", "-1", "-vn", "-c:a", "libmp3lame", "-q:a", "2", "-y", clean_temp2],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15
            )
            if res_encode.returncode == 0 and os.path.exists(clean_temp2) and os.path.getsize(clean_temp2) > 0:
                os.replace(clean_temp2, file_path)
                # Try applying tags again on the re-encoded clean file
                apply_tags(file_path)
                logger.success(f"🎵 MP3 qayta kodlangandan so'ng ID3 teglari va muqova rasmi yangilandi: Artist: '{artist}', Title: '{title}'")
            else:
                if os.path.exists(clean_temp2):
                    os.remove(clean_temp2)
                raise mutagen_err

    except Exception as e:
        logger.error(f"⚠️ MP3 teglarni yozishda xato: {e}")


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
    Foydalanuvchi qidiruv so'rovini target botga yuborishdan oldin keraksiz belgilar, linklar va reklamalardan tozalash.
    """
    if not query:
        return ""
    
    # 1. Qavslar ichidagi narsalarni olib tashlash (masalan: [MP3], (Official Video))
    cleaned = re.sub(r'[\(\[\{].*?[\)\]\}]', '', query)
    
    # 2. Telegram username-larini olib tashlash (masalan: @UzMuz, @baza_mp3)
    cleaned = re.sub(r'@[a-zA-Z0-9_]+', '', cleaned)
    
    # 3. URL va linklarni olib tashlash (masalan: t.me/..., http://...)
    cleaned = re.sub(r'(https?://)?(www\.)?[a-zA-Z0-9-]+\.[a-z]{2,}(/[a-zA-Z0-9_-]*)*', '', cleaned)
    
    # 4. Ortiqcha keraksiz reklama / yuklash so'zlarini tozalash (masalan: skachat, yuklash, mp3)
    promo_words = [
        r'\bskichat\b', r'\bskachat\b', r'\byuklash\b', r'\byuklab\b', r'\bolish\b',
        r'\bmp3\b', r'\bxit\b', r'\bhit\b', r'\brap\b', r'\bbass\b', r'\bbot\b',
        r'\bkanal\b', r'\bkanalimiz\b', r'\bobuna\b', r'\bbo\'ling\b', r'\bboling\b',
        r'\boriginal\b', r'\bofficial\b', r'\bklip\b', r'\bclip\b', r'\bvideo\b'
    ]
    for word_pat in promo_words:
        cleaned = re.sub(word_pat, '', cleaned, flags=re.IGNORECASE)
    
    # 5. Emojilarni olib tashlash (faqat harflar, raqamlar, ajratuvchilar qoladi)
    cleaned = re.sub(r'[^\w\s\-\.\']', '', cleaned)
    
    # 6. Ajratuvchi chiziqlarni normallashtirish (Artist-Title -> Artist - Title)
    cleaned = re.sub(r'\s*-\s*', ' - ', cleaned)
    
    # 7. Ortiqcha bo'shliqlarni olib tashlash
    cleaned = ' '.join(cleaned.split()).strip()
    
    # Agar juda qisqa yoki bo'sh bo'lsa, asl so'rovni qaytarish (xavfsizlik uchun)
    if len(cleaned) < 2:
        return query.strip()
        
    return cleaned


def extract_clean_artist_and_title(raw_artist: str, raw_title: str, caption: str = "", filename: str = "") -> tuple:
    """
    Manba kanal yuborgan musiqaning audio performer, title, caption va filename lari ichidan
    kanal reklamasi / suv belgilarini (masalan: Muzikalar UzMuz, Taronalar_qoshiqlar_mp3lar) olib tashlab,
    haqiqiy Artist va Qo'shiq nomini ajratib oladi.
    """
    raw_artist = (raw_artist or "").strip()
    raw_title = (raw_title or "").strip()
    caption = (caption or "").strip()
    filename = (filename or "").strip()

    promo_patterns = [
        r'muzikalar[\_\s]*uzmuz',
        r'taronalar[\_\s]*qoshiqlar[\_\s]*mp3lar',
        r'taronalar[\_\s]*qoshiqlar',
        r'uzmuz',
        r'taronalar',
        r'mp3lar',
        r'@[a-zA-Z0-9_]+',
        r't\.me/[a-zA-Z0-9_]+',
        r'https?://\S+',
        r'www\.[a-zA-Z0-9_-]+\.[a-z]+'
    ]

    # 1. Artist qismida reklama borligini aniqlash
    is_artist_promo = False
    if not raw_artist:
        is_artist_promo = True
    else:
        for pat in promo_patterns:
            if re.search(pat, raw_artist, re.IGNORECASE):
                is_artist_promo = True
                break

    final_artist = raw_artist
    final_title = raw_title

    # Agar title bo'sh bo'lsa yoki fayl nomi bo'lsa, filename yoki caption dan foydalanish
    if not final_title or final_title.endswith('.mp3'):
        if filename:
            final_title = filename.replace('.mp3', '')
        elif caption:
            final_title = caption

    # 2. Agar Artist reklama bo'lsa yoki bo'sh bo'lsa, lekin title yoki caption da " - " bo'lsa:
    if is_artist_promo or not final_artist:
        if " - " in raw_title:
            parts = raw_title.split(" - ", 1)
            final_artist = parts[0].strip()
            final_title = parts[1].strip()
        elif " - " in caption:
            parts = caption.split(" - ", 1)
            final_artist = parts[0].strip()
            final_title = parts[1].strip()
        elif " - " in filename:
            clean_fn = re.sub(r'^\s*muzikalar[\_\s]*uzmuz[\_\s]*', '', filename, flags=re.IGNORECASE)
            clean_fn = re.sub(r'[\_\s]*\d+\.mp3$', '.mp3', clean_fn, flags=re.IGNORECASE)
            clean_fn = clean_fn.replace('.mp3', '').replace('_', ' ')
            if " - " in clean_fn:
                parts = clean_fn.split(" - ", 1)
                final_artist = parts[0].strip()
                final_title = parts[1].strip()
            else:
                final_artist = ""
                final_title = clean_fn
        else:
            final_artist = ""

    # 3. Har bir satrdan reklama so'zlarini va qavslarni tozalash
    def clean_str(s):
        if not s:
            return ""
        s = re.sub(r'[\(\[\{].*?[\)\]\}]', '', s)  # Remove [MP3], (Official)
        s = re.sub(r'@[a-zA-Z0-9_]+', '', s)
        for pat in promo_patterns:
            s = re.sub(pat, '', s, flags=re.IGNORECASE)
        s = ' '.join(s.split()).strip()
        return s

    clean_artist = clean_str(final_artist)
    clean_title = clean_str(final_title)

    return clean_artist, clean_title



