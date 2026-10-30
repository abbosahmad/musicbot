"""AI orqali post matnlarini yozuvchi qism. AI ishlamasa zaxira matnlardan foydalanadi.

Uslub: bitta qisqa, ta'sirli jumla (sevgi, sadoqat, oila) - kanal postlari ostidagi blockquote uchun.
"""
import json
import random
import re
from typing import Dict, List, Optional

from loguru import logger
from openai import AsyncOpenAI

from . import settings

# Zaxira matnlar lotinda yoziladi, kerak bo'lsa kirillga o'giriladi
FALLBACK_LINES = [
    "Agar hayotimda nimadir abadiy bo'lsa, bu sening borliging bo'lsin!",
    "Har qanday holatda ham bir insonga sodiq qolmoqlikdir sevgi!",
    "Haqiqiy sevgi bu...",
    "Seni topganim — taqdirning eng chiroyli sovg'asi.",
    "Qo'limni tutgan qo'ling hech qachon qo'yib yubormasin.",
    "Baxt — sen bilan birga qarigan kunlarim bo'ladi.",
    "Sevgi so'zda emas, har kungi g'amxo'rlikda.",
    "Dunyo qanchalik katta bo'lmasin, mening dunyom — sensan.",
    "Nasib qilgan inson hech qachon begona bo'lmaydi.",
    "Yuragim faqat sening isming bilan tinchlanadi.",
    "Sabr qilgan sevgi albatta o'z egasini topadi.",
    "Bir umrlik hamroh — hayotning eng katta ne'mati.",
]

FALLBACK_VOICE_SCRIPTS = [
    "Bilasanmi, sevgi bu katta so'zlar emas. Sevgi bu charchaganingda choy damlab bergan, "
    "xafa bo'lganingda jim o'tirib quloq solgan inson. Shunday insoningiz bo'lsa, uni asrang.",
    "Har kim ham sizni sevishi shart emas. Lekin sizni chin yurakdan sevgan bitta inson "
    "butun dunyoga arziydi. Uni hech qachon yo'qotmang.",
]

_LAT2CYR_MULTI = [
    ("o'", "ў"), ("g'", "ғ"), ("O'", "Ў"), ("G'", "Ғ"),
    ("o‘", "ў"), ("g‘", "ғ"), ("O‘", "Ў"), ("G‘", "Ғ"),
    ("sh", "ш"), ("ch", "ч"), ("Sh", "Ш"), ("Ch", "Ч"), ("SH", "Ш"), ("CH", "Ч"),
    ("yo", "ё"), ("yu", "ю"), ("ya", "я"), ("Yo", "Ё"), ("Yu", "Ю"), ("Ya", "Я"),
    ("ye", "е"), ("Ye", "Е"),
]
_LAT2CYR_SINGLE = dict(zip(
    "abdefghijklmnopqrstuvxyzABDEFGHIJKLMNOPQRSTUVXYZ'’",
    "абдэфгҳижклмнопқрстувхйзАБДЭФГҲИЖКЛМНОПҚРСТУВХЙЗъъ",
))


def to_cyrillic(text: str) -> str:
    """O'zbek lotin -> kirill (zaxira matnlar uchun yetarli soddalashtirilgan o'giruvchi)."""
    out = []
    i = 0
    while i < len(text):
        pair = text[i:i + 2]
        for lat, cyr in _LAT2CYR_MULTI:
            if pair == lat:
                out.append(cyr)
                i += 2
                break
        else:
            ch = text[i]
            prev = text[i - 1] if i else " "
            # "e" so'z boshida "э", ichida "е"
            if ch in "eE":
                out.append(("э" if ch == "e" else "Э") if not prev.isalpha() else ("е" if ch == "e" else "Е"))
            else:
                out.append(_LAT2CYR_SINGLE.get(ch, ch))
            i += 1
    return "".join(out)


def _localize(text: str) -> str:
    return to_cyrillic(text) if settings.SCRIPT == "cyrillic" else text


def _script_name() -> str:
    return "o'zbek tili, KIRILL yozuvida" if settings.SCRIPT == "cyrillic" else "o'zbek tili, lotin yozuvida"


def _system_prompt() -> str:
    return f"""Siz Telegramdagi sevgi va oila mavzusidagi mashhur kanal uchun matn yozasiz.
Til: {_script_name()}. Mavzular: {settings.TOPICS}.

USLUB (juda muhim):
- Bitta qisqa, ta'sirli, yurakka tegadigan jumla (30-120 belgi). Ba'zan undov belgisi bilan tugaydi.
- Oddiy, samimiy, xalqona til - xuddi oddiy obunachi yozgandek. Kitobiy, rasmiy gaplar emas.
- Emoji, hashtag, havola, @username ishlatmang.
- Namuna: "Agar hayotimda nimadir abadiy bo'lsa, bu sening borliging bo'lsin!",
  "Har qanday holatda ham bir insonga sodiq qolmoqlikdir sevgi!", "Haqiqiy sevgi bu".

QAT'IY QOIDALAR:
- Diniy va siyosiy mavzular, haqorat, 18+ kontent yo'q.
- Mashhur shaxslarga iqtibos to'qib chiqarmang.
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
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": task + avoid},
            ],
            temperature=0.9,
        )
        return _extract_json(resp.choices[0].message.content or "")
    except Exception as e:
        logger.warning(f"AI matn yozishda xato, zaxira matn ishlatiladi: {e}")
        return None


_LINE_TASKS = {
    "quote": "Kanal uchun alohida matnli post: bitta aqlli, hikmatli gap yozing.",
    "clip": "Kanalga qisqa video (kino parcha, juftliklar, to'y lavhasi) joylanyapti. Uning ostiga bitta jumla yozing.",
    "voice": "Kanalga ovozli xabar joylanyapti. Uning ostiga bitta qisqa sarlavha-jumla yozing.",
    "music": "Kanalga qo'shiq joylanyapti. Uning ostiga kayfiyat beruvchi bitta jumla yozing (qo'shiq so'zlarini keltirmang).",
}


async def write_line(category: str, recent: List[str], hint: str = "") -> str:
    """Post ostidagi bitta qisqa jumla."""
    task = _LINE_TASKS[category]
    if hint:
        task += f"\nQo'shimcha ma'lumot: {hint}"
    data = await _ask_json(task + '\nFormat: {"text": "..."}', recent)
    if data and data.get("text"):
        return str(data["text"]).strip().strip('"«»')
    return _localize(random.choice(FALLBACK_LINES))


async def write_voice_script(recent: List[str]) -> Dict[str, str]:
    """AI ovozli xabar uchun: {'script': o'qiladigan matn, 'caption': ostidagi qisqa jumla}"""
    data = await _ask_json(
        "AI ovozi o'qib beradigan ovozli xabar matnini yozing: tinglovchiga murojaat qilingan, 3-5 gapdan "
        "iborat (400 belgigacha), sevgi, sadoqat yoki oila haqida samimiy fikr. Ovoz chiqarib o'qishga qulay "
        "bo'lsin, emoji va maxsus belgilarsiz. Shuningdek, xabar ostiga qo'yish uchun bitta qisqa jumla yozing.\n"
        'Format: {"script": "...", "caption": "..."}',
        recent,
    )
    if data and data.get("script"):
        return {"script": str(data["script"]).strip(), "caption": str(data.get("caption") or "").strip()}
    return {"script": _localize(random.choice(FALLBACK_VOICE_SCRIPTS)),
            "caption": _localize(random.choice(FALLBACK_LINES))}
