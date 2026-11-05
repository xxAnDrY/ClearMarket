"""Un giro completo su fonti simulate, senza rete."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from clearmarket.catalog import SOURCES
from clearmarket.markets import INSTRUMENTS, parse_chart, parse_spread, refresh_spread
from clearmarket.normalize import RawArticle, normalize
from clearmarket.run import add_articles, empty_state, is_visible, prune, public_files, run
from clearmarket.translate import (
    DEEPL_URL,
    MYMEMORY_URL,
    DeepLBackend,
    MyMemoryBackend,
    QuotaExceeded,
    TranslationError,
    build_backends,
    translate_pending,
)

NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
SOURCE = SOURCES[0]
CHART = {"chart": {"result": [{"meta": {"regularMarketPrice": 50505.87, "chartPreviousClose": 51031.02,
                                        "regularMarketTime": 1793896527}}]}}
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>{title}</title><link>https://x.example/a?utm_source=rss</link>
<description>&lt;p&gt;Testo.&lt;/p&gt;</description>
<pubDate>Thu, 05 Nov 2026 10:00:00 +0100</pubDate></item></channel></rss>"""


def make(title, url="https://x.example/1", at=NOW, language="it"):
    return normalize(RawArticle(title=title, url=url, published_at=at), source_slug=SOURCE.slug,
                     default_category="macro", language=language, now=NOW + timedelta(days=1))


def store(state, *items):
    return add_articles(state, SOURCE, list(items), NOW)


def test_same_url_is_ignored():
    state = empty_state()
    assert store(state, make("A")) == 1
    assert store(state, make("A")) == 0


def test_syndicated_title_is_linked_not_lost():
    state = empty_state()
    store(state, make("Fed holds rates steady"))
    store(state, make("Fed Holds Rates Steady - MarketWatch", "https://y.example/2", NOW + timedelta(hours=3)))
    assert len(state["articles"]) == 2
    assert sum(map(is_visible, state["articles"])) == 1


def test_same_title_months_later_is_new_news():
    state = empty_state()
    store(state, make("Fed holds rates steady", at=NOW - timedelta(days=20)))
    store(state, make("Fed holds rates steady", "https://y.example/2"))
    assert sum(map(is_visible, state["articles"])) == 2


@pytest.mark.parametrize("first,second,duplicate", [
    ("Nvidia shares jump after blowout quarterly earnings report",
     "Nvidia shares jump after blowout quarterly earnings", True),
    ("Apple shares rise 3% after earnings", "Apple shares rise 4% after earnings", False),
    ("Fed holds rates steady at December meeting", "ECB holds rates steady at December meeting", False),
])
def test_near_duplicates(first, second, duplicate):
    state = empty_state()
    store(state, make(first))
    store(state, make(second, "https://y.example/2", NOW + timedelta(hours=1)))
    assert sum(map(is_visible, state["articles"])) == (1 if duplicate else 2)


def test_very_old_items_are_ignored_and_retention_prunes():
    state = empty_state()
    assert store(state, make("Vecchia", at=NOW - timedelta(days=40))) == 0
    store(state, make("Nuova", at=NOW - timedelta(days=29)))
    prune(state, NOW + timedelta(days=2))
    assert state["articles"] == []


class Fake:
    daily_chars = 10_000

    def __init__(self, name="fake", error=None):
        self.name, self.error, self.calls = name, error, 0

    async def translate(self, texts, source):
        self.calls += 1
        if self.error:
            raise self.error
        return [f"IT {text}" for text in texts]


def pending(*titles):
    state = empty_state()
    for index, title in enumerate(titles):
        store(state, make(title, f"https://x.example/{index}", NOW + timedelta(minutes=index), "en"))
    return state["articles"]


async def test_foreign_articles_stay_hidden_until_translated():
    articles = pending("Stocks rally")
    assert articles[0]["translation_status"] == "pending" and not is_visible(articles[0])
    assert await translate_pending(articles, [Fake()], {}, "2026-11-05") == 1
    assert is_visible(articles[0]) and articles[0]["title"] == "IT Stocks rally"
    assert articles[0]["title_original"] == "Stocks rally"


async def test_second_backend_takes_over_on_quota():
    articles = pending("One", "Two")
    first, second = Fake("first", QuotaExceeded("q")), Fake("second")
    assert await translate_pending(articles, [first, second], {}, "2026-11-05") == 2
    assert first.calls == 1 and second.calls == 2


async def test_no_quota_keeps_articles_hidden_without_losing_attempts():
    articles = pending("One")
    assert await translate_pending(articles, [Fake("only", QuotaExceeded("q"))], {}, "2026-11-05") == 0
    assert articles[0]["translation_status"] == "pending" and articles[0]["translation_attempts"] == 0


async def test_daily_budget_stops_translation_and_resets_next_day():
    articles = pending("One", "Two")
    tiny = Fake()
    tiny.daily_chars = 3
    budget = {}
    assert await translate_pending(articles, [tiny], budget, "2026-11-05") == 1
    assert await translate_pending(articles, [tiny], budget, "2026-11-05") == 0
    assert await translate_pending(articles, [tiny], budget, "2026-11-06") == 1


async def test_repeated_errors_end_in_failed():
    articles = pending("One")
    for _ in range(5):
        await translate_pending(articles, [Fake("bad", TranslationError("x"))], {}, "2026-11-05")
    assert articles[0]["translation_status"] == "failed" and not is_visible(articles[0])


@respx.mock
async def test_mymemory_quota_warning_is_not_a_translation():
    respx.get(MYMEMORY_URL).mock(return_value=httpx.Response(200, json={
        "responseStatus": 429, "responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL"}}))
    async with httpx.AsyncClient() as client:
        with pytest.raises(QuotaExceeded):
            await MyMemoryBackend(client).translate(["Gold"], "en")


@respx.mock
async def test_deepl_request():
    route = respx.post(DEEPL_URL).mock(return_value=httpx.Response(200, json={"translations": [{"text": "Ciao"}]}))
    async with httpx.AsyncClient() as client:
        assert await DeepLBackend(client, "k:fx").translate(["Hello"], "en") == ["Ciao"]
        assert route.calls[0].request.headers["Authorization"] == "DeepL-Auth-Key k:fx"
        assert [backend.name for backend in build_backends(client, None)] == ["mymemory"]
        assert [backend.name for backend in build_backends(client, "k")] == ["deepl", "mymemory"]


@pytest.mark.parametrize("text,value", [
    ("Lo spread tra Btp e Bund chiude in rialzo a 109 punti base", 109),
    ("Pesano i tecnologici. Spread in rialzo a 108 punti", 108),
    ("Lo spread scende di 10 punti", None),
    ("Calmi euro e spread, in lieve recupero petrolio", None),
])
def test_parse_spread(text, value):
    assert parse_spread(text) == value


def test_spread_comes_from_italian_news_only():
    state = empty_state()
    quotes = {}
    store(state, make("Spread a 99 punti", language="en"))
    assert refresh_spread(state["articles"], quotes) is False
    store(state, make("Lo spread chiude a 109 punti", "https://y.example/2"))
    assert refresh_spread(state["articles"], quotes) is True
    assert quotes["BTP-BUND"]["value"] == 109 and quotes["BTP-BUND"]["change_pct"] is None


def test_parse_chart():
    assert parse_chart(CHART)[1] == -1.03


def test_public_feed_hides_pending_and_stale_quotes():
    state = empty_state()
    store(state, make("Italiana"), make("Foreign", "https://y.example/2", language="en"))
    state["quotes"]["OLD"] = {"order": 1, "as_of": (NOW - timedelta(days=8)).isoformat()}
    files = public_files(state, NOW)
    assert [item["title"] for item in files["feed.json"]["articles"]] == ["Italiana"]
    assert set(files["feed.json"]["articles"][0]) == {
        "id", "title", "summary", "source", "source_url", "translated", "published_at", "category",
        "related_tickers", "sentiment"}
    assert files["markets.json"]["quotes"] == []


def mock_network(rss_title="La Bce lascia i tassi invariati"):
    respx.get(url__regex=r".*(rss|feed|\.xml|\.html).*").mock(
        return_value=httpx.Response(200, text=RSS.format(title=rss_title), headers={"ETag": '"v1"'}))
    respx.get(url__regex=r"https://query1\.finance\.yahoo\.com/.*").mock(return_value=httpx.Response(200, json=CHART))
    respx.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json").mock(return_value=httpx.Response(200, json=[
        {"title": "CPI y/y", "country": "usd", "date": "2026-11-05T08:30:00-05:00", "impact": "High", "forecast": "3.1%"},
        {"title": "broken"}]))
    respx.get(MYMEMORY_URL).mock(return_value=httpx.Response(200, json={
        "responseStatus": 200, "responseData": {"translatedText": "Tradotto"}}))


@respx.mock
async def test_full_run_writes_site_files_and_second_run_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    mock_network()
    state = await run(tmp_path, NOW)
    assert len(state["articles"]) == 1  # stessa URL da tutte le fonti simulate
    feed = json.loads((tmp_path / "public/feed.json").read_text(encoding="utf-8"))
    assert feed["articles"][0]["source_url"] == "https://x.example/a"
    markets = json.loads((tmp_path / "public/markets.json").read_text(encoding="utf-8"))
    assert len(markets["quotes"]) == len(INSTRUMENTS)
    calendar = json.loads((tmp_path / "public/calendar.json").read_text(encoding="utf-8"))
    assert calendar["events"][0]["country"] == "USD"

    state = await run(tmp_path, NOW + timedelta(minutes=15))
    assert len(state["articles"]) == 1
    calls = [call for call in respx.calls if "ff_calendar" in str(call.request.url)]
    assert len(calls) == 1  # il calendario non si interroga a ogni giro
    rss = [call for call in respx.calls if "ilsole24ore.com/rss/economia" in str(call.request.url)]
    assert rss[-1].request.headers["If-None-Match"] == '"v1"'


@respx.mock
async def test_broken_source_is_isolated_and_rate_limit_is_respected(tmp_path, monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    respx.get("https://www.ansa.it/sito/notizie/economia/economia_rss.xml").mock(return_value=httpx.Response(500))
    respx.get("https://www.finanzaonline.com/feed").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "7200"}))
    mock_network()
    state = await run(tmp_path, NOW)
    assert state["sources"]["ansa-economia"]["failures"] == 1
    assert state["sources"]["finanzaonline"]["skip_until"]
    assert state["articles"]
    await run(tmp_path, NOW + timedelta(minutes=15))
    assert sum("finanzaonline" in str(call.request.url) for call in respx.calls) == 1


async def test_finnhub_is_skipped_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url__regex=r"https://finnhub\.io/.*").mock(return_value=httpx.Response(200, json=[]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(500))
        await run(tmp_path, NOW)
    assert not route.called
