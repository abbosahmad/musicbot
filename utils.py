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
        logger.error(f"AI xatoligi (Fallback ishlatiladi): {e}")
        return {"artist": _clean_single_string(raw_artist), "title": _clean_single_string(raw_title)}

# --- 2. YouTube API va yt-dlp ---

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
            'videoCategoryId': '10',  # Music category
            'order': 'relevance'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if 'items' in data and data['items']:
                        # Eng yaxshi variantni tanlash
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
    YouTube API dan olingan URL orqali fayl yuklash (cookies'siz)
    """
    try:
        logger.info(f"YouTube'dan yuklanmoqda: {youtube_url}")
        
        ydl_opts = {
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
            # Cookies'siz ishlash uchun
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web_embedded', 'tv_embedded'],
                    'skip': ['dash', 'hls']
                }
            },
            # User-Agent o'zgartirish
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Android 11; Mobile; rv:68.0) Gecko/68.0 Firefox/88.0'
            },
            # Kechikish qo'shish
            'sleep_interval': 2,
            'max_sleep_interval': 5,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(youtube_url, download=True)
                filename = ydl.prepare_filename(info)
                final_filename = os.path.splitext(filename)[0] + ".mp3"
                
                if os.path.exists(final_filename):
                    logger.success("✅ YouTube'dan muvaffaqiyatli yuklandi!")
                    return final_filename
                else:
                    logger.error("Yuklangan fayl topilmadi")
                    return None
            except Exception as e:
                # Agar hali ham ishlamasa, boshqa usulni sinab ko'ramiz
                logger.warning(f"Birinchi usul ishlamadi: {e}")
                
                # 2-usul: Minimal sozlamalar
                ydl_opts_minimal = {
                    'format': 'worst[ext=mp4]/worst',
                    'outtmpl': 'downloads/yt_minimal_%(id)s.%(ext)s',
                    'quiet': True,
                    'no_warnings': True,
                    'ignoreerrors': True,
                }
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_minimal) as ydl_minimal:
                        info = ydl_minimal.extract_info(youtube_url, download=True)
                        filename = ydl_minimal.prepare_filename(info)
                        
                        if os.path.exists(filename):
                            logger.success("✅ Minimal usul bilan yuklandi!")
                            return filename
                        else:
                            logger.error("Minimal usul ham ishlamadi")
                            return None
                except Exception as e2:
                    logger.error(f"Minimal usul xatosi: {e2}")
                    return None
                
    except Exception as e:
        logger.error(f"YouTube yuklashda umumiy xato: {e}")
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
    downloaded_file = download_youtube_with_api_url(youtube_url)
    
    if downloaded_file:
        return downloaded_file
    
    # 3. Agar YouTube ishlamasa, boshqa qidiruv urinishi
    logger.warning("YouTube yuklash ishlamadi. Boshqa variantni sinab ko'ramiz...")
    
    # Boshqa qidiruv so'zi bilan
    alternative_query = f"{artist} {title} audio"
    alternative_result = await search_youtube_with_api_by_query(alternative_query)
    
    if alternative_result:
        alternative_url = alternative_result['url']
        alternative_file = download_youtube_with_api_url(alternative_url)
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

def download_best_match_from_youtube(artist: str, title: str, target_duration_sec: int = 0) -> str:
    """
    YouTube'dan xatoga chidamli yuklash funksiyasi.
    """
    search_query = f"{artist} - {title} Official Audio"
    logger.info(f"YouTube qidiruv: {search_query}")
    
    # Cookies faylini tekshirish
    cookies_file = 'cookies.txt'
    if not os.path.exists(cookies_file):
        logger.warning("cookies.txt topilmadi. YouTube yuklash ishlamasligi mumkin.")
        return None
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'default_search': 'ytsearch3',  # Faqat 3 ta natija
        'cookiefile': cookies_file,
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'no_warnings': True,
        # YouTube bot aniqlashdan qochish uchun
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web_embedded', 'tv_embedded'],
                'skip': ['dash', 'hls']
            }
        },
        # User-Agent o'zgartirish
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 1. Ma'lumot qidirish
            try:
                logger.info("YouTube'da qidirilmoqda...")
                results = ydl.extract_info(search_query, download=False)
            except Exception as e:
                logger.error(f"YouTube qidiruvida xato: {e}")
                # Agar cookies muammosi bo'lsa, usiz sinab ko'ramiz
                if "cookies" in str(e).lower() or "sign in" in str(e).lower():
                    logger.warning("Cookies muammosi. Usiz sinab ko'rilmoqda...")
                    ydl_opts.pop('cookiefile', None)
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl_no_cookies:
                            results = ydl_no_cookies.extract_info(search_query, download=False)
                    except Exception as e2:
                        logger.error(f"Cookies usiz ham ishlamadi: {e2}")
                        return None
                else:
                    return None

            if not results or 'entries' not in results:
                logger.warning("YouTube hech narsa topmadi.")
                return None

            best_url = None
            
            # 2. Eng yaxshi variantni tanlash
            for entry in results['entries']:
                if not entry: continue
                vid_duration = entry.get('duration', 0)
                title_vid = entry.get('title', '')
                
                logger.info(f"Variant: {title_vid[:50]}... | Vaqt: {vid_duration}s")
                
                # Davomiyligi mos kelsa
                if target_duration_sec > 0:
                    diff = abs(vid_duration - target_duration_sec)
                    if diff < 30:  # 30 soniya farq
                        best_url = entry['webpage_url']
                        break
                else:
                    # Birinchi yaxshi variantni olish
                    if vid_duration > 60:  # Kamida 1 daqiqa
                        best_url = entry['webpage_url']
                        break
            
            # 3. Agar topilmasa, birinchisini olish
            if not best_url and results['entries']:
                if results['entries'][0]:
                    best_url = results['entries'][0]['webpage_url']

            # 4. Yuklash
            if best_url:
                logger.info(f"YouTube'dan yuklanmoqda: {best_url}")
                ydl_opts['outtmpl'] = 'downloads/clean_%(id)s.%(ext)s'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',  # Sifatni pasaytirdik
                }]
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl_down:
                        info = ydl_down.extract_info(best_url, download=True)
                        filename = ydl_down.prepare_filename(info)
                        final_filename = os.path.splitext(filename)[0] + ".mp3"
                        
                        if os.path.exists(final_filename):
                            logger.success("✅ YouTube'dan muvaffaqiyatli yuklandi!")
                            return final_filename
                        else:
                            logger.error("Yuklangan fayl topilmadi")
                            return None
                            
                except Exception as e:
                    logger.error(f"YouTube yuklashda xato: {e}")
                    return None
            else:
                logger.warning("YouTube'da mos variant topilmadi")
                return None
                    
    except Exception as e:
        logger.error(f"YouTube yuklashda umumiy xato: {e}")
        return None
    
    return None

# --- Yordamchi ---

def _clean_single_string(text: str) -> str:
    if not text: return ""
    cleaned_text = re.sub(r'[\(\[\{].*?[\)\]\}]', '', text)
    cleaned_text = re.sub(r'@[a-zA-Z0-9_]+', '', cleaned_text)
    return ' '.join(cleaned_text.split()).strip()

def clean_title(title: str, artist: str) -> str:
    return f"{artist} - {title}"

def get_daily_post_count() -> int:
    return 6  # Kuniga 6 ta musiqa

def calculate_post_times(count: int) -> list:
    if count == 0: return []
    tashkent_tz = pytz.timezone("Asia/Tashkent")
    now = datetime.now(tashkent_tz)
    start_time = now + timedelta(minutes=5)  # 5 daqiqa keyin boshlash
    
    # Har 3 soatda post (6 ta bo'lsa: 0, 3, 6, 9, 12, 15 soatlarda)
    times = [start_time + timedelta(hours=i*3) for i in range(count)]
    return times
