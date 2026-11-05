"""Un giro completo su fonti simulate, senza rete."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from clearmarkets.catalog import SOURCES
from clearmarkets.markets import INSTRUMENTS, parse_chart, parse_spread, refresh_spread
from clearmarkets.normalize import RawArticle, normalize
from clearmarkets.run import add_articles, empty_state, is_visible, load_state, prune, public_files, run
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
    store(state, make("Fed holds rates steady", at=NOW - timedelta(days=10)))
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


def test_foreign_articles_stay_in_english_and_are_visible():
    state = empty_state()
    store(state, make("Stocks rally on Wall Street", language="en"))
    article = public_files(state, NOW)["feed.json"]["articles"][0]
    assert article["title"] == "Stocks rally on Wall Street" and article["language"] == "en"


def test_old_state_format_is_discarded(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"articles": [{"title": "vecchio"}]}), encoding="utf-8")
    assert load_state(path) == empty_state()


def test_catalog_slugs_are_unique_and_cover_both_languages():
    slugs = [source.slug for source in SOURCES]
    assert len(slugs) == len(set(slugs))
    assert {source.language for source in SOURCES} == {"it", "en"}


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


def test_public_feed_hides_duplicates_and_stale_quotes():
    state = empty_state()
    store(state, make("Italiana"), make("Italiana", "https://y.example/2"))
    state["quotes"]["OLD"] = {"order": 1, "as_of": (NOW - timedelta(days=8)).isoformat()}
    files = public_files(state, NOW)
    assert [item["title"] for item in files["feed.json"]["articles"]] == ["Italiana"]
    assert set(files["feed.json"]["articles"][0]) == {
        "id", "title", "summary", "source", "source_url", "language", "published_at", "category",
        "related_tickers", "sentiment"}
    assert files["markets.json"]["quotes"] == []


def mock_network(rss_title="La Bce lascia i tassi invariati"):
    respx.get(url__regex=r".*(rss|feed|\.xml|\.html).*").mock(
        return_value=httpx.Response(200, text=RSS.format(title=rss_title), headers={"ETag": '"v1"'}))
    respx.get(url__regex=r"https://query1\.finance\.yahoo\.com/.*").mock(return_value=httpx.Response(200, json=CHART))


@respx.mock
async def test_full_run_writes_site_files_and_second_run_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    mock_network()
    state = await run(tmp_path, NOW)
    assert len(state["articles"]) == 1  # stessa URL da tutte le fonti simulate
    feed = json.loads((tmp_path / "public/feed.json").read_text(encoding="utf-8"))
    assert feed["articles"][0]["source_url"] == "https://x.example/a"
    markets = json.loads((tmp_path / "public/markets.json").read_text(encoding="utf-8"))
    assert len(markets["quotes"]) == len(INSTRUMENTS)
    assert sorted(path.name for path in (tmp_path / "public").iterdir()) == ["feed.json", "markets.json"]

    state = await run(tmp_path, NOW + timedelta(minutes=15))
    assert len(state["articles"]) == 1
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
