"""AI orqali post matnlarini yozuvchi qism. AI ishlamasa zaxira matnlardan foydalanadi."""
import json
import random
import re
from typing import Dict, List, Optional

from loguru import logger
from openai import AsyncOpenAI

from . import settings

FALLBACK_QUOTES = [
    {"quote": "Sabr achchiq, lekin uning mevasi shirin.", "author": "Xalq maqoli",
     "comment": "Bugun qiyin bo'lsa ham, ertangi kun uchun chidab turing."},
    {"quote": "Vaqt — qaytarib bo'lmaydigan yagona boylik.", "author": "",
     "comment": "Uni kimga va nimaga sarflayotganingizga e'tibor bering."},
    {"quote": "Do'st kulfatda bilinadi.", "author": "Xalq maqoli",
     "comment": "Yoningizda qolganlarni qadrlang."},
    {"quote": "Ming eshitgandan bir ko'rgan yaxshi.", "author": "Xalq maqoli",
     "comment": "Bugun bir narsani o'z ko'zingiz bilan sinab ko'ring."},
    {"quote": "Kichik qadam ham — oldinga qadam.", "author": "",
     "comment": "Mukammal paytni kutmang, hozir boshlang."},
    {"quote": "Ota-onaning duosi — eng katta boylik.", "author": "",
     "comment": "Bugun ularga qo'ng'iroq qilishni unutmang."},
    {"quote": "Yaxshi so'z — jon ozig'i.", "author": "Xalq maqoli",
     "comment": "Bir iliq so'z kimningdir kunini yorug' qilishi mumkin."},
    {"quote": "Yiqilish — mag'lubiyat emas, turmaslik — mag'lubiyat.", "author": "",
     "comment": "Har bir xato sizni tajribali qiladi."},
    {"quote": "O'zgalarga qanday munosabatda bo'lsang, shunday munosabat ko'rasan.", "author": "",
     "comment": "Hayot — aks-sado kabi."},
    {"quote": "Ilm — tuganmas xazina.", "author": "Xalq maqoli",
     "comment": "Bugun yangi bir narsani o'rganing."},
    {"quote": "Sokinlik ham javob bo'la oladi.", "author": "",
     "comment": "Har bir gapga javob berish shart emas."},
    {"quote": "Baxt — kichik narsalarni payqay olishda.", "author": "",
     "comment": "Bir piyola choy, yaqin inson suhbati... yetarli emasmi?"},
]

FALLBACK_CLIP_CAPTIONS = [
    "Ba'zi sahnalar so'zsiz ham ko'p narsani aytadi...",
    "Shu lavhani ko'rib, o'ylanib qoldim.",
    "Kinodagi bu daqiqa — hayotning o'zi.",
    "Ayrim gaplarni faqat kino shunday chiroyli ayta oladi.",
]

FALLBACK_MUSIC_CAPTIONS = [
    "Bugungi kayfiyat uchun 🎧",
    "Shu qo'shiq bilan dam oling.",
    "Quloqqa ham, yurakka ham yoqimli.",
    "Kechki choy va shu musiqa ☕️",
]

_SYSTEM_PROMPT = f"""Siz Telegram kanal uchun kontent yozuvchi muallifsiz.
Til: {settings.LANGUAGE}. Uslub: samimiy, qisqa, chuqur ma'noli, o'quvchini o'ylantiradigan.
Mavzular: {settings.TOPICS}.

QAT'IY QOIDALAR:
- Diniy va siyosiy mavzularga tegmang.
- Haqorat, nafrat, 18+ kontent yo'q.
- Iqtibos muallifini faqat 100% ishonchingiz komil bo'lsa yozing, aks holda muallif bo'sh qolsin. Hech qachon muallifni to'qib chiqarmang.
- Hashtag, havola, @username ishlatmang.
- Faqat so'ralgan JSON formatida javob qaytaring, boshqa hech narsa yozmang."""


def _make_client(api_key: str, base_url: Optional[str], model: str) -> AsyncOpenAI:
    if not base_url:
        if "openrouter" in model.lower():
            base_url = "https://openrouter.ai/api/v1"
        elif "deepseek" in model.lower() and not model.startswith("gpt"):
            base_url = "https://api.deepseek.com"
    return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0)


def _extract_json(text: str) -> Dict:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError("JSON topilmadi")
    return json.loads(match.group(0))


async def _ask_json(task: str, recent: List[str]) -> Optional[Dict]:
    if not settings.AI_API_KEY:
        return None
    avoid = ""
    if recent:
        avoid = "\n\nOxirgi postlar (bularni takrorlamang, yangi fikr yozing):\n" + "\n".join(
            f"- {t[:150]}" for t in recent
        )
    try:
        client = _make_client(settings.AI_API_KEY, settings.AI_BASE_URL, settings.AI_MODEL)
        resp = await client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": task + avoid},
            ],
            temperature=0.9,
        )
        return _extract_json(resp.choices[0].message.content or "")
    except Exception as e:
        logger.warning(f"AI matn yozishda xato, zaxira matn ishlatiladi: {e}")
        return None


async def write_quote(recent: List[str]) -> Dict[str, str]:
    """{'quote', 'author', 'comment'}"""
    data = await _ask_json(
        "Kanal uchun bitta aqlli gap (iqtibos yoki hikmatli so'z) va unga 1-2 gapdan iborat "
        "qisqa izoh yozing. Iqtibos 200 belgidan oshmasin.\n"
        'Format: {"quote": "...", "author": "...", "comment": "..."}',
        recent,
    )
    if data and data.get("quote"):
        return {k: str(data.get(k) or "").strip() for k in ("quote", "author", "comment")}
    return dict(random.choice(FALLBACK_QUOTES))


async def write_clip_caption(note: str, recent: List[str]) -> str:
    data = await _ask_json(
        "Kanalga kinodan parcha (video) joylanyapti. Unga 1-3 gapdan iborat ta'sirli, "
        "o'ylantiruvchi izoh yozing (300 belgigacha). Kino nomini bilmasangiz, uni to'qimang.\n"
        f"Admin izohi / kino haqida ma'lumot: {note or 'yoq'}\n"
        'Format: {"caption": "..."}',
        recent,
    )
    if data and data.get("caption"):
        return str(data["caption"]).strip()
    return random.choice(FALLBACK_CLIP_CAPTIONS)


async def write_music_caption(title: str, note: str, recent: List[str]) -> str:
    data = await _ask_json(
        "Kanalga musiqa joylanyapti. Unga kayfiyat beruvchi 1-2 gapli qisqa izoh yozing (200 belgigacha). "
        "Qo'shiq so'zlarini keltirmang.\n"
        f"Qo'shiq: {title or 'nomalum'}. Admin izohi: {note or 'yoq'}\n"
        'Format: {"caption": "..."}',
        recent,
    )
    if data and data.get("caption"):
        return str(data["caption"]).strip()
    return random.choice(FALLBACK_MUSIC_CAPTIONS)


async def write_voice_script(recent: List[str]) -> Dict[str, str]:
    """Ovozli xabar uchun: {'script': o'qiladigan matn, 'caption': ostidagi qisqa yozuv}"""
    data = await _ask_json(
        "Kanal uchun ovozli xabar matnini yozing: tinglovchiga murojaat qilingan, 3-5 gapdan iborat "
        "(400 belgigacha) samimiy, motivatsion yoki hayotiy fikr. Ovoz chiqarib o'qishga qulay bo'lsin, "
        "emoji va maxsus belgilarsiz. Shuningdek, xabar ostiga qo'yish uchun bitta qisqa sarlavha yozing.\n"
        'Format: {"script": "...", "caption": "..."}',
        recent,
    )
    if data and data.get("script"):
        return {"script": str(data["script"]).strip(), "caption": str(data.get("caption") or "").strip()}
    q = random.choice(FALLBACK_QUOTES)
    return {"script": f"{q['quote']} {q['comment']}", "caption": "Bugungi fikr"}
