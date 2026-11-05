"""Regole italiane, polling per fasce orarie e coda di traduzione."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from app.config import Settings
from app.ingestion.normalize import RawArticle, classify, extract_tickers, normalize, score_sentiment
from app.ingestion.schedule import is_market_open, next_market_open, next_poll_delay
from app.ingestion.translate import (
    DeepLBackend,
    MyMemoryBackend,
    QuotaExceeded,
    TranslationError,
    TranslationQueue,
    build_backends,
)
from app.ingestion.worker import store_articles

ROME = ZoneInfo("Europe/Rome")
NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
SETTINGS = Settings(database_url="postgresql://unused", _env_file=None)
THURSDAY = (2026, 11, 5)


def rome(*parts):
    return datetime(*parts, tzinfo=ROME)


@pytest.mark.parametrize("moment,expected", [
    (rome(*THURSDAY, 8, 29), False),
    (rome(*THURSDAY, 8, 30), True),
    (rome(*THURSDAY, 22, 29), True),
    (rome(*THURSDAY, 22, 30), False),
    (rome(2026, 11, 7, 12, 0), False),   # sabato
    (rome(2026, 11, 8, 12, 0), False),   # domenica
])
def test_market_hours(moment, expected):
    assert is_market_open(moment) is expected


def test_friday_night_waits_for_monday():
    opening = next_market_open(rome(2026, 11, 6, 23, 0))
    assert opening == rome(2026, 11, 9, 8, 30)


def test_open_and_closed_intervals():
    assert next_poll_delay(rome(*THURSDAY, 12, 0), 300, 1800) == 300
    assert next_poll_delay(rome(2026, 11, 7, 12, 0), 300, 1800) == 1800


def test_closed_interval_does_not_skip_the_opening():
    assert next_poll_delay(rome(*THURSDAY, 8, 20), 300, 3600) == 600


def test_interval_after_clock_change_uses_local_time():
    # Il 25 ottobre 2026 l'ora legale finisce: l'apertura resta alle 8:30 locali.
    assert next_market_open(rome(2026, 10, 24, 23, 0)) == rome(2026, 10, 26, 8, 30)


@pytest.mark.parametrize("text,category", [
    ("La Bce lascia i tassi di interesse invariati", "monetary_policy"),
    ("Inflazione in calo a ottobre secondo l'Istat", "macro"),
    ("Manovra, il governo trova l'accordo sulle tasse", "fiscal_policy"),
    ("Spread Btp-Bund in calo", "bonds"),
    ("Il petrolio Brent torna sopra 80 dollari", "commodities"),
    ("Oil prices rise as OPEC cuts output", "commodities"),
    ("Consumi delle famiglie in aumento, salari fermi", "microeconomics"),
    ("Piazza Affari chiude in rialzo", "stocks_eu"),
    ("Wall Street apre in calo", "stocks_us"),
])
def test_italian_and_new_categories(text, category):
    assert classify(text, [], "macro") == category


@pytest.mark.parametrize("title,label", [
    ("Crollo di Piazza Affari, banche in forte ribasso", "negative"),
    ("Rimbalzo delle Borse, il Ftse Mib vola", "positive"),
    ("La Banca d'Italia pubblica il bollettino", "neutral"),
    ("Borse senza rimbalzo", "negative"),
])
def test_italian_sentiment(title, label):
    assert score_sentiment(title)[0] == label


def test_italian_tickers_and_common_words():
    assert set(extract_tickers("Mediobanca e Banco BPM in rialzo")) == {"MB.MI", "BAMI.MI"}
    assert extract_tickers("Elezioni generali in vista") == []


def test_foreign_article_is_queued_and_keeps_the_original():
    article = normalize(
        RawArticle(title="Stocks fall", url="https://x.example/a", published_at=NOW),
        source_id=1, default_category="macro", language="en", now=NOW)
    assert article.translation_status == "pending" and article.title_original == "Stocks fall"
    assert article.sentiment == "negative"


class FakeBackend:
    def __init__(self, name="fake", error=None):
        self.name, self.error, self.calls = name, error, 0

    async def translate(self, texts, source):
        self.calls += 1
        if self.error:
            raise self.error
        return [f"IT {text}" for text in texts]


async def queue_article(pool, title="Stocks rally", summary="A strong day"):
    sid = await pool.fetchval("SELECT id FROM sources WHERE slug = 'bloomberg-markets'")
    article = normalize(RawArticle(title=title, url=f"https://x.example/{title}", summary=summary,
                                   published_at=NOW),
                        source_id=sid, default_category="macro", language="en", now=NOW)
    await store_articles(pool, [article], SETTINGS)


async def test_pending_article_stays_hidden_until_translated(pool):
    await queue_article(pool)
    assert await pool.fetchval("SELECT visible FROM articles") is False

    assert await TranslationQueue(pool, [FakeBackend()], 5).run_once() == 1
    row = await pool.fetchrow("SELECT * FROM articles")
    assert row["visible"] is True and row["translated_by"] == "fake"
    assert row["title"] == "IT Stocks rally" and row["summary"] == "IT A strong day"
    assert row["title_original"] == "Stocks rally"


async def test_second_backend_takes_over_when_quota_is_exhausted(pool):
    await queue_article(pool, "One")
    await queue_article(pool, "Two")
    exhausted, spare = FakeBackend("first", QuotaExceeded("quota")), FakeBackend("second")
    queue = TranslationQueue(pool, [exhausted, spare], 5)
    assert await queue.run_once() == 2
    assert exhausted.calls == 1 and spare.calls == 2  # il primo resta in pausa


async def test_without_backends_nothing_is_published_and_no_attempt_is_lost(pool):
    await queue_article(pool)
    queue = TranslationQueue(pool, [FakeBackend("only", QuotaExceeded("quota"))], 5)
    assert await queue.run_once() == 0
    row = await pool.fetchrow("SELECT * FROM articles")
    assert row["translation_status"] == "pending" and row["translation_attempts"] == 0
    assert row["visible"] is False


async def test_repeated_errors_end_in_failed_and_stay_hidden(pool):
    await queue_article(pool)
    queue = TranslationQueue(pool, [FakeBackend("bad", TranslationError("boom"))], 5)
    for _ in range(5):
        await queue.run_once()
        await pool.execute("UPDATE articles SET translate_after = now()")
    row = await pool.fetchrow("SELECT * FROM articles")
    assert row["translation_status"] == "failed" and row["visible"] is False


async def test_two_replicas_do_not_translate_the_same_article(pool):
    await queue_article(pool)
    first, second = FakeBackend("a"), FakeBackend("b")
    await TranslationQueue(pool, [first], 5).run_once()
    await TranslationQueue(pool, [second], 5).run_once()
    assert first.calls == 1 and second.calls == 0


@respx.mock
async def test_mymemory_parses_and_unescapes():
    respx.get(MyMemoryBackend.URL).mock(return_value=httpx.Response(200, json={
        "responseStatus": 200, "responseData": {"translatedText": "L&#39;oro sale"}}))
    async with httpx.AsyncClient() as client:
        assert await MyMemoryBackend(client).translate(["Gold rises"], "en") == ["L'oro sale"]


@respx.mock
async def test_mymemory_quota_warning_inside_a_200_is_not_a_translation():
    respx.get(MyMemoryBackend.URL).mock(return_value=httpx.Response(200, json={
        "responseStatus": 429,
        "responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS"}}))
    async with httpx.AsyncClient() as client:
        with pytest.raises(QuotaExceeded):
            await MyMemoryBackend(client).translate(["Gold rises"], "en")


@respx.mock
async def test_deepl_request_and_quota():
    url = "https://api-free.deepl.com/v2/translate"
    route = respx.post(url).mock(return_value=httpx.Response(200, json={
        "translations": [{"text": "Ciao"}]}))
    async with httpx.AsyncClient() as client:
        backend = DeepLBackend(client, "key:fx", url)
        assert await backend.translate(["Hello"], "en") == ["Ciao"]
        assert route.calls[0].request.headers["Authorization"] == "DeepL-Auth-Key key:fx"
        route.mock(return_value=httpx.Response(456))
        with pytest.raises(QuotaExceeded):
            await backend.translate(["Hello"], "en")


def test_deepl_is_skipped_without_a_key():
    settings = SETTINGS.model_copy(update={"translation_backends": "deepl,mymemory"})
    assert [backend.name for backend in build_backends(settings, None)] == ["mymemory"]
