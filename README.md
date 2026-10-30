# 🎵 Music Telegram Bot

A powerful **Telegram Music Bot** built with Python and Aiogram. Allows users to search and download music directly in Telegram.

## ✨ Features

- 🔍 Search music by name
- ⬇️ Download songs from YouTube
- 🎧 Send audio files directly to Telegram chat
- 👤 User management system
- 🌐 Web admin panel integration
- 🍪 YouTube cookie support for restricted content

## 🛠️ Tech Stack

- **Language:** Python 3.10+
- **Framework:** Aiogram 3.x
- **Music Source:** YouTube (yt-dlp)
- **Database:** SQLite / PostgreSQL
- **Hosting:** Linux VPS

## 🚀 Getting Started

### Prerequisites
```bash
python >= 3.10
pip install -r requirements.txt
```

### Setup
```bash
git clone https://github.com/AbbosPC/musicbot.git
cd musicbot
cp config.py.example config.py
# Add your BOT_TOKEN in config.py
python main.py
```

## 📁 Project Structure
```
musicbot/
├── main.py          # Bot entry point
├── config.py        # Configuration
├── templates/       # HTML templates
└── .gitignore
```

## 👨‍💻 Author

**Abbos Ahmad** — Full Stack & Telegram Bot Developer
- 🔗 Upwork: [abbos-ahmad](https://www.upwork.com/freelancers/~015a754b7ac9da6a9b)
- 💬 Telegram: [@abbosahmad](https://t.me/abbosahmad)

## 📄 License

MIT License

---

## 🤖 Kanal Post Agenti (`post_agent/`)

Kanalga kun davomida **aralash** postlar joylab boruvchi alohida agent:

| Tur | Manba |
|-----|-------|
| 🎬 Kino parcha / qisqa video | Admin botga yuborgan / forward qilgan video, GIF, dumaloq video |
| 🎙 Ovozli xabar | Admin yozgan voice yoki AI ovozi (OpenAI TTS) |
| 🎵 Musiqa | Admin yuborgan audio |
| 💡 Aqlli gap | Faqat matnli post (AI yozadi) |

**Post uslubi:** media + ostida bitta qisqa, ta'sirli jumla `blockquote` ichida
(masalan: *«Агар ҳаётимда нимадир абадий бўлса, бу сенинг борлигинг бўлсин!»*).
- Media bilan caption yuborsangiz — post aynan shu caption bilan chiqadi.
- Boshqa kanaldan forward qilinsa — caption'dagi @username, havola va hashtag'lar tozalanadi.
- Caption bo'lmasa — jumlani AI yozadi (oxirgi postlar takrorlanmaydi), AI bo'lmasa zaxira jumlalar.

Agent turlarni og'irlik (ulush) bo'yicha tanlaydi va bir xil turni ketma-ket qo'ymaydi.
Kutubxonadagi eng kam ishlatilgan media birinchi joylanadi.

### Ishga tushirish
```bash
pip install -r requirements.txt
python -m post_agent
```
Botga `/start` yozing — boshqaruv tugmalari chiqadi. Media yuborsangiz kutubxonaga qo'shiladi
(caption yozsangiz, post shu caption bilan chiqadi).

Buyruqlar: `/post [quote|clip|voice|music]`, `/preview [tur]`, `/stats`.

### `.env` sozlamalari
```env
AGENT_BOT_TOKEN=...            # alohida bot tavsiya etiladi (bo'lmasa ADMIN_BOT_TOKEN)
AGENT_ADMIN_ID=123456789       # bo'lmasa ADMIN_USER_ID
AGENT_CHANNEL_ID=-100...       # bot kanalda admin bo'lishi shart
AGENT_SIGNATURE=               # bo'sh qoldirsangiz imzo qo'shilmaydi
AGENT_SCRIPT=cyrillic          # yoki latin
AGENT_POST_TIMES=08:00,11:00,14:00,17:00,20:00,22:30
AGENT_JITTER_SECONDS=300       # vaqtga +/- tasodifiy siljish
AGENT_MIX=clip:5,voice:2,music:2,quote:1
AGENT_TOPICS=sevgi, sadoqat, oila, nasib, sog'inch, juftlik baxti
OPENAI_API_KEY=...             # matn va TTS uchun (AI_MODEL / AI_BASE_URL ham ishlaydi)
AGENT_TTS_ENABLED=true
AGENT_TTS_MODEL=gpt-4o-mini-tts
AGENT_TTS_VOICE=onyx
```

Testlar: `pytest test_post_agent.py`
