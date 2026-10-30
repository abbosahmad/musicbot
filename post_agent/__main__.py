"""Ishga tushirish: python -m post_agent"""
import asyncio
import html
import re

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from . import settings, tts
from .publisher import CATEGORIES, Publisher
from .storage import CATEGORY_LABELS, Storage

logger.add("post_agent.log", rotation="1 week", retention="1 month", level="INFO", encoding="utf-8")

dp = Dispatcher()
storage = Storage(settings.DB_PATH)
publisher: Publisher  # main() ichida yaratiladi


def is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_USER_ID


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Hozir post (avto)", callback_data="post:auto"),
         InlineKeyboardButton(text="👁 Namuna", callback_data="prev:auto")],
        [InlineKeyboardButton(text=CATEGORY_LABELS["quote"], callback_data="post:quote"),
         InlineKeyboardButton(text=CATEGORY_LABELS["clip"], callback_data="post:clip")],
        [InlineKeyboardButton(text=CATEGORY_LABELS["voice"], callback_data="post:voice"),
         InlineKeyboardButton(text=CATEGORY_LABELS["music"], callback_data="post:music")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
    ])


def media_keyboard(media_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 Hozir joylash", callback_data=f"mpost:{media_id}"),
        InlineKeyboardButton(text="👁 Namuna", callback_data=f"mprev:{media_id}"),
        InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"mdel:{media_id}"),
    ]])


async def stats_text() -> str:
    counts = await storage.count_by_category()
    lines = ["📊 <b>Kutubxona</b>"]
    for cat in ("clip", "voice", "music"):
        c = counts.get(cat, {"total": 0, "unused": 0})
        lines.append(f"{CATEGORY_LABELS[cat]}: {c['total']} ta (ishlatilmagan: {c['unused']})")
    lines.append(f"\n🎙 AI ovoz (TTS): {'yoqilgan ✅' if tts.is_available() else 'o‘chiq ❌'}")
    lines.append(f"📝 Jami postlar: {await storage.post_count()}")
    lines.append(f"🕒 Jadval: {', '.join(settings.POST_TIMES)} ({settings.TIMEZONE})")
    mix = ", ".join(f"{CATEGORY_LABELS.get(k, k)} {v}" for k, v in settings.MIX.items())
    lines.append(f"⚖️ Ulush: {mix}")
    return "\n".join(lines)


HELP_TEXT = (
    "🤖 <b>Kanal post agenti</b>\n\n"
    "Men kanalga navbat bilan aralash postlar joylayman:\n"
    "🎬 kino parchalar / qisqa videolar\n"
    "💡 aqlli gaplar (AI yozadi)\n"
    "🎙 ovozli xabarlar (siz yozgan yoki AI ovozi)\n"
    "🎵 musiqalar\n\n"
    "<b>Kutubxonaga qo'shish:</b> menga video, GIF, dumaloq video, ovozli xabar yoki audio "
    "yuboring (yoki boshqa kanaldan forward qiling).\n"
    "• Caption yozsangiz — post aynan shu caption bilan chiqadi (formatlash ham saqlanadi).\n"
    "• Caption bo'lmasa — AI qisqa jumla yozib, blockquote ichida qo'yadi.\n\n"
    "<b>Buyruqlar:</b>\n"
    "/post [quote|clip|voice|music] — hozir kanalga joylash\n"
    "/preview [tur] — kanalga emas, o'zingizga namuna\n"
    "/stats — statistika"
)


@dp.message(Command("start", "help"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(HELP_TEXT, reply_markup=main_keyboard())


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(await stats_text())


def _parse_category(arg: str):
    arg = (arg or "").strip().lower()
    if not arg or arg == "auto":
        return None, True
    return (arg, True) if arg in CATEGORIES else (None, False)


@dp.message(Command("post", "preview"))
async def cmd_post(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    category, ok = _parse_category(command.args)
    if not ok:
        await message.answer(f"Tur noto'g'ri. Mavjud turlar: {', '.join(CATEGORIES)}")
        return
    chat_id = message.chat.id if command.command == "preview" else None
    success, info = await publisher.publish(category, chat_id=chat_id)
    if chat_id is None or not success:
        await message.answer(f"✅ Joylandi: {CATEGORY_LABELS.get(info, info)}" if success else f"❌ {info}")


@dp.callback_query(F.data.startswith(("post:", "prev:")))
async def cb_post(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    action, arg = call.data.split(":", 1)
    category, _ = _parse_category(arg)
    await call.answer("⏳ Tayyorlanmoqda...")
    chat_id = call.message.chat.id if action == "prev" else None
    success, info = await publisher.publish(category, chat_id=chat_id)
    if chat_id is None or not success:
        await call.message.answer(f"✅ Joylandi: {CATEGORY_LABELS.get(info, info)}" if success else f"❌ {info}")


@dp.callback_query(F.data.startswith(("mpost:", "mprev:", "mdel:")))
async def cb_media(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    action, raw_id = call.data.split(":", 1)
    media_id = int(raw_id)
    if action == "mdel":
        deleted = await storage.delete_media(media_id)
        await call.answer("🗑 O'chirildi" if deleted else "Topilmadi")
        if deleted:
            await call.message.edit_reply_markup(reply_markup=None)
        return
    if not await storage.get_media(media_id):
        return await call.answer("Bu media o'chirilgan", show_alert=True)
    await call.answer("⏳ Tayyorlanmoqda...")
    chat_id = call.message.chat.id if action == "mprev" else None
    success, info = await publisher.publish(chat_id=chat_id, media_id=media_id)
    if chat_id is None or not success:
        await call.message.answer(f"✅ Joylandi: {CATEGORY_LABELS.get(info, info)}" if success else f"❌ {info}")


def clean_forwarded_caption(text: str) -> str:
    """Boshqa kanaldan forward qilingan caption'dan havola, @username va reklama qatorlarini olib tashlaydi."""
    lines = []
    for line in (text or "").splitlines():
        if re.search(r"(@\w+|t\.me/|https?://|www\.)", line, re.IGNORECASE):
            continue
        line = re.sub(r"#\w+", "", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def caption_note(message: Message) -> str:
    if not message.caption:
        return ""
    if message.forward_origin:
        cleaned = clean_forwarded_caption(message.caption)
        return f"<blockquote>{html.escape(cleaned)}</blockquote>" if cleaned else ""
    return message.html_text


@dp.message(F.video | F.animation | F.video_note | F.voice | F.audio)
async def on_media(message: Message):
    if not is_admin(message.from_user.id):
        return
    # animation xabarida document ham bo'ladi, shuning uchun avval animation tekshiriladi
    for kind in ("animation", "video", "video_note", "voice", "audio"):
        obj = getattr(message, kind)
        if obj:
            break
    title = ""
    if kind == "audio":
        title = " - ".join(p for p in (obj.performer, obj.title) if p) or (obj.file_name or "")
    media_id = await storage.add_media(kind, obj.file_id, obj.file_unique_id,
                                       title=title, note=caption_note(message))
    if media_id is None:
        await message.reply("ℹ️ Bu fayl kutubxonada allaqachon bor.")
        return
    media = await storage.get_media(media_id)
    await message.reply(
        f"✅ Kutubxonaga qo'shildi: {CATEGORY_LABELS[media['category']]} (#{media_id})",
        reply_markup=media_keyboard(media_id),
    )


async def scheduled_post():
    success, info = await publisher.publish()
    if not success:
        logger.warning(f"Rejali post yuborilmadi: {info}")
        try:
            await publisher.bot.send_message(settings.ADMIN_USER_ID, f"⚠️ Rejali post yuborilmadi: {info}")
        except Exception:
            pass


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)
    for t in settings.POST_TIMES:
        hour, minute = t.split(":")
        scheduler.add_job(
            scheduled_post,
            CronTrigger(hour=int(hour), minute=int(minute), timezone=settings.TIMEZONE,
                        jitter=settings.JITTER_SECONDS or None),
            misfire_grace_time=600,
        )
    return scheduler


async def main():
    global publisher
    if not settings.BOT_TOKEN:
        raise SystemExit("AGENT_BOT_TOKEN (yoki ADMIN_BOT_TOKEN) .env faylida ko'rsatilmagan")
    if not settings.ADMIN_USER_ID:
        raise SystemExit("AGENT_ADMIN_ID (yoki ADMIN_USER_ID) .env faylida ko'rsatilmagan")
    if not settings.CHANNEL_ID:
        logger.warning("AGENT_CHANNEL_ID ko'rsatilmagan - faqat /preview ishlaydi")

    await storage.connect()
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    publisher = Publisher(bot, storage)

    scheduler = setup_scheduler()
    scheduler.start()
    logger.info(f"Post agent ishga tushdi. Jadval: {settings.POST_TIMES}")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
