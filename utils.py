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
from shazamio import Shazam
import aiohttp

import config

# --- 1. AI Integratsiyasi (DeepSeek V3) ---

async def get_clean_details_with_ai(raw_artist: str, raw_title: str) -> dict:
    if not hasattr(config, 'DEEPSEEK_API_KEY') or not config.DEEPSEEK_API_KEY:
        return {"artist": _clean_single_string(raw_artist), "title": _clean_single_string(raw_title)}

    try:
        client = AsyncOpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )

        system_prompt = """You are a music metadata cleaning expert. 
Your task is to extract the clean 'artist' and 'title' from raw input.
- Remove ads, channel names (@...), URLs, 'Official Video', 'MP3', emojis.
- Fix capitalization (Title Case).
- If the artist is inside the title, extract it.
- Return ONLY a JSON object: {"artist": "...", "title": "..."}"""

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
             
        return {"artist": _clean_single_string(raw_artist), "title": _clean_single_string(raw_title)}

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
    try:
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
    cleaned_text = re.sub(r'[\(\[\{].*?[\)\]\}]', '', text)
    cleaned_text = re.sub(r'@[a-zA-Z0-9_]+', '', cleaned_text)
    return ' '.join(cleaned_text.split()).strip()


def clean_title(title: str, artist: str) -> str:
    return f"{artist} - {title}"


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
