# test_post_agent.py - post_agent uchun tarmoqsiz testlar (pytest test_post_agent.py)
import asyncio
import random
from types import SimpleNamespace

import pytest

from post_agent import publisher as pub_module
from post_agent import settings
from post_agent.publisher import Publisher, available_categories, choose_category, format_line
from post_agent.writer import to_cyrillic
from post_agent.storage import Storage


class FakeBot:
    def __init__(self):
        self.sent = []
        self._id = 0

    def _record(self, method, chat_id, payload, **kw):
        self._id += 1
        self.sent.append((method, chat_id, payload, kw))
        return SimpleNamespace(message_id=self._id)

    async def send_message(self, chat_id, text, **kw):
        return self._record("message", chat_id, text, **kw)

    async def send_video(self, chat_id, file_id, **kw):
        return self._record("video", chat_id, file_id, **kw)

    async def send_animation(self, chat_id, file_id, **kw):
        return self._record("animation", chat_id, file_id, **kw)

    async def send_video_note(self, chat_id, file_id, **kw):
        return self._record("video_note", chat_id, file_id, **kw)

    async def send_voice(self, chat_id, file_id, **kw):
        return self._record("voice", chat_id, file_id, **kw)

    async def send_audio(self, chat_id, file_id, **kw):
        return self._record("audio", chat_id, file_id, **kw)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "AI_API_KEY", None)
    monkeypatch.setattr(settings, "TTS_ENABLED", False)
    monkeypatch.setattr(settings, "CHANNEL_ID", -100123)
    monkeypatch.setattr(settings, "SIGNATURE", "@test_kanal")

    async def make():
        storage = Storage(str(tmp_path / "agent.db"))
        await storage.connect()
        return storage, FakeBot()

    return make


def run(coro):
    return asyncio.run(coro)


def test_choose_category_avoids_repeat():
    rng = random.Random(1)
    mix = {"quote": 3, "clip": 2, "voice": 2, "music": 3}
    for _ in range(50):
        assert choose_category(["quote", "music"], mix, "music", rng) == "quote"


def test_choose_category_respects_zero_weight():
    rng = random.Random(2)
    picks = {choose_category(["quote", "clip"], {"quote": 0, "clip": 1}, None, rng) for _ in range(30)}
    assert picks == {"clip"}


def test_available_categories():
    assert available_categories({}, False) == ["quote"]
    assert available_categories({}, True) == ["quote", "voice"]
    counts = {"clip": {"total": 1, "unused": 1}, "music": {"total": 2, "unused": 0}}
    assert available_categories(counts, False) == ["quote", "clip", "music"]


def test_format_line_blockquote(monkeypatch):
    monkeypatch.setattr(settings, "SIGNATURE", "")
    assert format_line("a < b & c") == "<blockquote>a &lt; b &amp; c</blockquote>"


def test_to_cyrillic():
    assert to_cyrillic("Haqiqiy sevgi bu") == "Ҳақиқий севги бу"
    assert to_cyrillic("Har qanday holatda sodiq qolmoqlik") == "Ҳар қандай ҳолатда содиқ қолмоқлик"
    assert to_cyrillic("O'zbek g'ururi, shirin choy, yoshlik, ertak") == "Ўзбек ғурури, ширин чой, ёшлик, эртак"


def test_admin_caption_used_verbatim(env):
    async def scenario():
        storage, bot = await env()
        mid = await storage.add_media("video", "vid", "u1", note="<b>Mr&amp;Mrs</b>")
        ok, _ = await Publisher(bot, storage).publish(media_id=mid)
        assert ok
        assert bot.sent[0][3]["caption"] == "<b>Mr&amp;Mrs</b>\n\n@test_kanal"
        await storage.close()

    run(scenario())


def test_media_dedup_and_rotation(env):
    async def scenario():
        storage, _ = await env()
        a = await storage.add_media("video", "f1", "u1", note="Kino 1")
        assert await storage.add_media("video", "f1", "u1") is None
        b = await storage.add_media("animation", "f2", "u2")
        await storage.mark_used(a)
        picked = await storage.pick_media("clip")
        assert picked["id"] == b
        counts = await storage.count_by_category()
        assert counts["clip"] == {"total": 2, "unused": 1}
        await storage.close()

    run(scenario())


def test_publish_mix_without_ai(env):
    async def scenario():
        storage, bot = await env()
        await storage.add_media("video", "vid", "u1")
        await storage.add_media("audio", "aud", "u2", title="Artist - Song")
        await storage.add_media("voice", "voi", "u3", note="haqiqiy sevgi bu")
        p = Publisher(bot, storage)

        for cat in ("quote", "clip", "voice", "music"):
            ok, info = await p.publish(cat)
            assert ok, info

        methods = [s[0] for s in bot.sent]
        assert methods == ["message", "video", "voice", "audio"]
        assert all(s[1] == -100123 for s in bot.sent)
        assert bot.sent[0][2].startswith("<blockquote>") and "@test_kanal" in bot.sent[0][2]
        assert bot.sent[1][3]["caption"].startswith("<blockquote>")  # AI/zaxira jumla
        assert bot.sent[2][3]["caption"].startswith("haqiqiy sevgi bu")  # admin caption
        assert await storage.post_count() == 4
        assert (await storage.count_by_category())["clip"]["unused"] == 0
        await storage.close()

    run(scenario())


def test_preview_does_not_record(env):
    async def scenario():
        storage, bot = await env()
        p = Publisher(bot, storage)
        ok, _ = await p.publish("quote", chat_id=42)
        assert ok and bot.sent[0][1] == 42
        assert await storage.post_count() == 0
        await storage.close()

    run(scenario())


def test_missing_media_reports_error(env):
    async def scenario():
        storage, bot = await env()
        ok, info = await Publisher(bot, storage).publish("music")
        assert not ok and "musiqa" in info
        await storage.close()

    run(scenario())


def test_voice_uses_tts_when_library_exhausted(env, monkeypatch):
    async def fake_synth(text):
        return b"OggS-fake"

    async def scenario():
        storage, bot = await env()
        monkeypatch.setattr(pub_module.tts, "is_available", lambda: True)
        monkeypatch.setattr(pub_module.tts, "synthesize", fake_synth)
        ok, _ = await Publisher(bot, storage).publish("voice")
        assert ok
        method, _, payload, _ = bot.sent[0]
        assert method == "voice" and payload.filename == "voice.ogg"
        await storage.close()

    run(scenario())
