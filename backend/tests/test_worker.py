"""Worker contro Postgres reale, con le fonti HTTP simulate da respx."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.config import Settings
from app.ingestion.normalize import RawArticle, normalize
from app.ingestion.worker import Worker, store_articles, watched_symbols

NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
SETTINGS = Settings(database_url="postgresql://unused", finnhub_api_key="k", _env_file=None)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>ECB keeps rates unchanged</title><link>https://ecb.example/a?utm_source=rss</link>
<description>&lt;p&gt;The Governing Council decided.&lt;/p&gt;</description>
<pubDate>Thu, 05 Nov 2026 10:00:00 +0100</pubDate></item>
<item><title>Annual report published</title><link>https://ecb.example/b</link>
<pubDate>Thu, 05 Nov 2026 09:00:00 +0100</pubDate></item>
</channel></rss>"""


async def source_id(pool, slug):
    return await pool.fetchval("SELECT id FROM sources WHERE slug = $1", slug)


async def only_due(pool, *slugs):
    await pool.execute("UPDATE sources SET next_poll_at = now() + interval '1 day'")
    await pool.execute("UPDATE sources SET next_poll_at = now() WHERE slug = ANY($1)", list(slugs))


def make(sid, title, url, at=NOW):
    return normalize(RawArticle(title=title, url=url, published_at=at),
                     source_id=sid, default_category="macro", now=NOW + timedelta(days=30))


@pytest.fixture
def worker_factory(pool, redis):
    clients = []

    def factory():
        client = httpx.AsyncClient()
        clients.append(client)
        return Worker(SETTINGS, pool, redis, client)
    return factory


@respx.mock
async def test_rss_ingestion_is_idempotent_and_uses_conditional_get(pool, redis, worker_factory):
    await only_due(pool, "ecb-press")
    await pool.execute("UPDATE sources SET language = 'it' WHERE slug = 'ecb-press'")
    route = respx.get("https://www.ecb.europa.eu/rss/press.html").mock(
        return_value=httpx.Response(200, text=RSS, headers={"ETag": '"v1"'}))
    worker = worker_factory()

    assert await worker.run_once() == 1
    rows = await pool.fetch("SELECT title, summary, source_url, category, published_at FROM articles ORDER BY published_at")
    assert [row["title"] for row in rows] == ["Annual report published", "ECB keeps rates unchanged"]
    assert rows[1]["source_url"] == "https://ecb.example/a"              # tracking rimosso
    assert rows[1]["summary"] == "The Governing Council decided."  # HTML rimosso
    assert rows[1]["published_at"] == datetime(2026, 11, 5, 9, tzinfo=timezone.utc)
    assert {row["category"] for row in rows} == {"monetary_policy"}
    assert await redis.get("feed:version") == "1"

    # Secondo giro: stessa risposta, nessun nuovo articolo e nessuna invalidazione.
    await only_due(pool, "ecb-press")
    await worker.run_once()
    assert await pool.fetchval("SELECT count(*) FROM articles") == 2
    assert await redis.get("feed:version") == "1"
    assert route.calls[-1].request.headers["If-None-Match"] == '"v1"'

    # 304: fonte sana, ETag conservato.
    route.mock(return_value=httpx.Response(304))
    await only_due(pool, "ecb-press")
    await worker.run_once()
    row = await pool.fetchrow("SELECT http_etag, consecutive_failures FROM sources WHERE slug='ecb-press'")
    assert row["http_etag"] == '"v1"' and row["consecutive_failures"] == 0
    await pool.execute("UPDATE sources SET language = 'en' WHERE slug = 'ecb-press'")


@respx.mock
async def test_failure_backs_off_and_one_bad_source_does_not_stop_others(pool, worker_factory):
    await only_due(pool, "ecb-press", "fed-press")
    respx.get("https://www.ecb.europa.eu/rss/press.html").mock(return_value=httpx.Response(500))
    respx.get("https://www.federalreserve.gov/feeds/press_all.xml").mock(
        return_value=httpx.Response(200, text=RSS))
    await worker_factory().run_once()

    failed = await pool.fetchrow(
        "SELECT consecutive_failures, last_error, next_poll_at - now() AS delay FROM sources WHERE slug='ecb-press'")
    assert failed["consecutive_failures"] == 1
    assert "500" in failed["last_error"]
    assert failed["delay"] > timedelta(seconds=500)  # 300s * 2^1 meno jitter
    assert await pool.fetchval("SELECT count(*) FROM articles") == 2


@respx.mock
async def test_rate_limit_honours_retry_after(pool, worker_factory):
    await only_due(pool, "ecb-press")
    respx.get("https://www.ecb.europa.eu/rss/press.html").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "900"}))
    await worker_factory().run_once()
    row = await pool.fetchrow(
        "SELECT consecutive_failures, next_poll_at - now() AS delay FROM sources WHERE slug='ecb-press'")
    assert row["delay"] > timedelta(seconds=800)
    assert row["consecutive_failures"] == 0


@respx.mock
async def test_finnhub_news_normalizes_and_advances_min_id(pool, worker_factory):
    await only_due(pool, "finnhub-general")
    route = respx.get("https://finnhub.io/api/v1/news").mock(return_value=httpx.Response(200, json=[
        {"id": 7, "headline": "Nvidia jumps on demand", "url": "https://x.example/1", "summary": "",
         "datetime": 1793880000, "related": ""},
        {"id": 9, "headline": "CPI cools further", "url": "https://x.example/2", "summary": "s",
         "datetime": 1793880100, "related": "SPY, QQQ"},
    ]))
    worker = worker_factory()
    await worker.run_once()

    request = route.calls[0].request
    assert request.headers["X-Finnhub-Token"] == "k"
    assert "token" not in str(request.url)  # la chiave non deve finire nei log
    assert request.url.params["category"] == "general"
    rows = {r["title"]: r for r in await pool.fetch("SELECT * FROM articles")}
    assert rows["Nvidia jumps on demand"]["related_tickers"] == ["NVDA"]
    assert rows["Nvidia jumps on demand"]["sentiment"] == "positive"
    assert rows["CPI cools further"]["related_tickers"] == ["SPY", "QQQ"]
    assert rows["CPI cools further"]["category"] == "macro"
    assert await pool.fetchval("SELECT provider_cursor FROM sources WHERE slug='finnhub-general'") == "9"

    await only_due(pool, "finnhub-general")
    await worker.run_once()
    second = route.calls[-1].request.url.params
    assert second["minId"] == "9" and second["category"] == "general"


@respx.mock
async def test_company_news_rotates_and_tolerates_plan_restrictions(pool, worker_factory):
    await pool.execute(
        """INSERT INTO user_watchlist (user_id, ticker) VALUES
           (gen_random_uuid(), 'AAPL'), (gen_random_uuid(), 'SAP.DE')""")
    await only_due(pool, "finnhub-company")

    def respond(request):
        if request.url.params["symbol"] == "SAP.DE":
            return httpx.Response(403, json={"error": "no access"})
        return httpx.Response(200, json=[{"headline": "Quarterly numbers out", "url": "https://x.example/q",
                                          "datetime": 1793880000, "related": "AAPL"}])
    respx.get("https://finnhub.io/api/v1/company-news").mock(side_effect=respond)
    await worker_factory().run_once()

    assert await pool.fetchval("SELECT related_tickers FROM articles") == ["AAPL"]
    assert await pool.fetchval("SELECT consecutive_failures FROM sources WHERE slug='finnhub-company'") == 0


async def test_watched_symbols_rotation_covers_everything(pool):
    await pool.execute(
        "INSERT INTO user_watchlist (user_id, ticker) SELECT gen_random_uuid(), t FROM unnest($1::text[]) t",
        ["A", "B", "C", "D", "E"])
    seen = set()
    offset = 0
    for _ in range(3):
        batch = await watched_symbols(pool, offset, 2)
        seen.update(batch)
        offset += len(batch)
    assert seen == {"A", "B", "C", "D", "E"}


@respx.mock
async def test_calendar_upsert_updates_actual_without_duplicating(pool, worker_factory):
    await only_due(pool, "ff-calendar")
    event = {"title": "CPI y/y", "country": "usd", "date": "2026-11-05T08:30:00-05:00",
             "impact": "High", "forecast": "3.1%", "previous": "3.0%"}
    route = respx.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json").mock(
        return_value=httpx.Response(200, json=[event, {"title": "broken"}]))
    worker = worker_factory()
    await worker.run_once()

    route.mock(return_value=httpx.Response(200, json=[{**event, "actual": "3.2%"}]))
    await only_due(pool, "ff-calendar")
    await worker.run_once()

    rows = await pool.fetch("SELECT * FROM economic_events")
    assert len(rows) == 1
    assert rows[0]["actual"] == "3.2%" and rows[0]["impact"] == "high" and rows[0]["country"] == "USD"
    assert rows[0]["starts_at"] == datetime(2026, 11, 5, 13, 30, tzinfo=timezone.utc)


async def test_syndicated_title_is_linked_not_lost(pool):
    a, b = await source_id(pool, "cnbc-investing"), await source_id(pool, "cnbc-economy")
    assert await store_articles(pool, [make(a, "Fed holds rates steady", "https://a.example/1")], SETTINGS) == 1
    assert await store_articles(
        pool, [make(b, "Fed Holds Rates Steady - MarketWatch", "https://b.example/9", NOW + timedelta(hours=3))],
        SETTINGS) == 0
    assert await pool.fetchval("SELECT count(*) FROM articles") == 2
    assert await pool.fetchval("SELECT count(*) FROM articles WHERE duplicate_of IS NULL") == 1


async def test_same_title_months_later_is_new_news(pool):
    a = await source_id(pool, "cnbc-investing")
    await store_articles(pool, [make(a, "Fed holds rates steady", "https://a.example/1")], SETTINGS)
    later = make(a, "Fed holds rates steady", "https://a.example/2", NOW + timedelta(days=90))
    assert await store_articles(pool, [later], SETTINGS) == 1


@pytest.mark.parametrize("first,second,duplicate", [
    # Stessa notizia riscritta.
    ("Nvidia shares jump after blowout quarterly earnings report",
     "Nvidia shares jump after blowout quarterly earnings", True),
    # Titolo con il suffisso della testata.
    ("Nvidia shares jump after earnings", "Nvidia shares jump after earnings - Bloomberg", True),
    # Numeri diversi: notizie diverse anche se il testo e' quasi identico.
    ("Apple shares rise 3% after earnings", "Apple shares rise 4% after earnings", False),
    # Soggetto diverso.
    ("Fed holds rates steady at December meeting", "ECB holds rates steady at December meeting", False),
])
async def test_near_duplicate_decisions(pool, first, second, duplicate):
    a = await source_id(pool, "cnbc-investing")
    await store_articles(pool, [make(a, first, "https://a.example/1")], SETTINGS)
    visible = await store_articles(
        pool, [make(a, second, "https://a.example/2", NOW + timedelta(hours=1))], SETTINGS)
    assert visible == (0 if duplicate else 1)


async def test_concurrent_workers_never_claim_the_same_source(pool, redis, worker_factory):
    await only_due(pool, "ecb-press")
    from app.ingestion.worker import _CLAIM_SQL
    first = await pool.fetch(_CLAIM_SQL, 4, 120.0)
    second = await pool.fetch(_CLAIM_SQL, 4, 120.0)
    assert len(first) == 1 and second == []
