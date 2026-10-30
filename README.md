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
| 💡 Aqlli gap | AI yozadi (takrorlanmasligi uchun oxirgi postlar hisobga olinadi), AI bo'lmasa — zaxira hikmatlar |
| 🎬 Kino parcha | Admin botga yuborgan / forward qilgan video, GIF, dumaloq video + AI izoh |
| 🎙 Ovozli xabar | Admin yozgan voice yoki AI ovozi (OpenAI TTS) |
| 🎵 Musiqa | Admin yuborgan audio + AI kayfiyat izohi |

Agent turlarni og'irlik (ulush) bo'yicha tanlaydi va bir xil turni ketma-ket qo'ymaydi.
Kutubxonadagi eng kam ishlatilgan media birinchi joylanadi.

### Ishga tushirish
```bash
pip install -r requirements.txt
python -m post_agent
```
Botga `/start` yozing — boshqaruv tugmalari chiqadi. Media yuborsangiz kutubxonaga qo'shiladi
(caption'ga kino nomi yoki izoh yozsangiz, AI undan foydalanadi).

Buyruqlar: `/post [quote|clip|voice|music]`, `/preview [tur]`, `/stats`.

### `.env` sozlamalari
```env
AGENT_BOT_TOKEN=...            # alohida bot tavsiya etiladi (bo'lmasa ADMIN_BOT_TOKEN)
AGENT_ADMIN_ID=123456789       # bo'lmasa ADMIN_USER_ID
AGENT_CHANNEL_ID=-100...       # bot kanalda admin bo'lishi shart
AGENT_SIGNATURE=🌙 @kanalim
AGENT_POST_TIMES=08:00,11:00,14:00,17:00,20:00,22:30
AGENT_JITTER_SECONDS=300       # vaqtga +/- tasodifiy siljish
AGENT_MIX=quote:3,clip:2,voice:2,music:3
AGENT_TOPICS=hayot, sabr, sevgi, motivatsiya
OPENAI_API_KEY=...             # matn va TTS uchun (AI_MODEL / AI_BASE_URL ham ishlaydi)
AGENT_TTS_ENABLED=true
AGENT_TTS_MODEL=gpt-4o-mini-tts
AGENT_TTS_VOICE=onyx
```

Testlar: `pytest test_post_agent.py`
