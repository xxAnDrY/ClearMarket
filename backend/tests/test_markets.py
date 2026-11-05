from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.config import get_settings
from app.ingestion.markets import (
    INSTRUMENTS,
    YAHOO_URL,
    fetch_markets,
    parse_chart,
    parse_spread,
    refresh_quotes,
    refresh_spread,
)
from app.ingestion.normalize import RawArticle, normalize
from app.ingestion.worker import store_articles
from test_api import client  # noqa: F401 - fixture condivisa

CHART = {"chart": {"result": [{"meta": {"regularMarketPrice": 50505.87, "chartPreviousClose": 51031.02,
                                        "regularMarketTime": 1793896527}}]}}


def test_parse_chart():
    price, change, as_of = parse_chart(CHART)
    assert price == 50505.87 and change == -1.03 and as_of.tzinfo is not None


@pytest.mark.parametrize("text,value", [
    ("Lo spread tra Btp e Bund chiude in rialzo a 109 punti base", 109),
    ("Lo spread tra Btp e Bund apre poco mosso a 105 punti", 105),
    ("Pesano i tecnologici. Spread in rialzo a 108 punti", 108),
    ("Lo spread scende di 10 punti", None),
    ("Calmi euro e spread, in lieve recupero petrolio", None),
])
def test_parse_spread(text, value):
    assert parse_spread(text) == value


@respx.mock
async def test_refresh_keeps_last_value_when_a_source_fails(pool):
    await pool.execute("TRUNCATE market_quotes")
    route = respx.get(url__regex=r"https://query1\.finance\.yahoo\.com/.*").mock(
        return_value=httpx.Response(200, json=CHART))
    async with httpx.AsyncClient() as http:
        assert await refresh_quotes(pool, http) == len(INSTRUMENTS)
        route.mock(return_value=httpx.Response(429))
        assert await refresh_quotes(pool, http) == 0
    assert "%5EGSPC" in str(route.calls[1].request.url)
    assert YAHOO_URL.split("{")[0] in str(route.calls[0].request.url)
    assert len(await fetch_markets(pool)) == len(INSTRUMENTS)


async def add_article(pool, title):
    sid = await pool.fetchval("SELECT id FROM sources WHERE slug = 'ansa-economia'")
    now = datetime.now(timezone.utc)
    await store_articles(pool, [normalize(
        RawArticle(title=title, url=f"https://x.example/{hash(title)}", published_at=now - timedelta(minutes=5)),
        source_id=sid, default_category="macro", now=now)], get_settings())


async def test_spread_comes_from_real_news_and_is_absent_without_it(pool):
    await pool.execute("TRUNCATE market_quotes")
    assert await refresh_spread(pool) is False
    assert await fetch_markets(pool) == []
    await add_article(pool, "Lo spread tra Btp e Bund chiude a 109 punti base")
    assert await refresh_spread(pool) is True
    quote = (await fetch_markets(pool))[0]
    assert quote["value"] == 109 and quote["unit"] == "pb" and quote["change_pct"] is None


async def test_stale_quotes_disappear(pool):
    await pool.execute("TRUNCATE market_quotes")
    await pool.execute(
        """INSERT INTO market_quotes (symbol, label, value, as_of)
           VALUES ('OLD', 'Vecchio', 1, now() - interval '8 days')""")
    assert await fetch_markets(pool) == []


async def test_markets_endpoint_reports_quotes_and_status(client, pool):  # noqa: F811
    await pool.execute("TRUNCATE market_quotes")
    body = (await client.get("/api/v1/markets")).json()
    assert body["quotes"] == [] and isinstance(body["market_open"], bool)


async def test_search_matches_text_and_tickers_and_escapes_wildcards(client, pool):  # noqa: F811
    await add_article(pool, "Lo spread tra Btp e Bund chiude a 109 punti base")
    await add_article(pool, "Nvidia guida il listino")
    found = (await client.get("/api/v1/feed", params={"q": "spread tra"})).json()["data"]
    assert [item["title"][:9] for item in found] == ["Lo spread"]
    by_ticker = (await client.get("/api/v1/feed", params={"q": "nvda"})).json()["data"]
    assert [item["related_tickers"] for item in by_ticker] == [["NVDA"]]
    assert (await client.get("/api/v1/feed", params={"q": "%%"})).json()["data"] == []
    assert (await client.get("/api/v1/feed", params={"q": "x"})).status_code == 422
