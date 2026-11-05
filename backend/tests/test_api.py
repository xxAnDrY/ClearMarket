"""API end-to-end su Postgres reale."""
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
from redis.exceptions import ConnectionError as RedisConnectionError

from app.cache import bump_feed_version
from app.config import get_settings
from app.ingestion.normalize import RawArticle, normalize
from app.ingestion.worker import store_articles
from app.main import app
from app.ratelimit import TokenBucket, allow_request

NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def client(pool, redis) -> AsyncIterator[httpx.AsyncClient]:
    app.state.pool, app.state.redis, app.state.jwks = pool, redis, None
    app.state.settings = get_settings()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def seed(pool, count=5, *, category="macro", title="Item", tickers=(), start=NOW):
    sid = await pool.fetchval("SELECT id FROM sources WHERE slug = 'cnbc-investing'")
    articles = [normalize(
        RawArticle(title=f"{title} {uuid4().hex}", url=f"https://x.example/{uuid4().hex}",
                   published_at=start - timedelta(minutes=index), tickers=tickers),
        source_id=sid, default_category=category, lock_category=True,
        now=NOW + timedelta(days=1)) for index in range(count)]
    settings = get_settings()
    await store_articles(pool, articles, settings)


def token(user: UUID, *, expired=False, audience="authenticated", secret=None) -> dict:
    claims = {"sub": str(user), "aud": audience,
              "exp": int(time.time()) + (-60 if expired else 600)}
    encoded = jwt.encode(claims, secret or get_settings().jwt_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {encoded}"}


async def test_payload_shape(client, pool):
    await seed(pool, 1, tickers=("AAPL",))
    body = (await client.get("/api/v1/feed")).json()
    item = body["data"][0]
    assert set(item) == {"id", "title", "summary", "source", "source_url", "translated",
                         "published_at", "category", "related_tickers", "sentiment"}
    assert item["source_url"].startswith("https://x.example/") and item["translated"] is False
    assert item["source"] == {"slug": "cnbc-investing", "name": "CNBC"}
    assert item["sentiment"]["label"] in {"positive", "neutral", "negative"}
    assert item["related_tickers"] == ["AAPL"]
    assert body["page_info"] == {"next_cursor": None, "has_more": False, "limit": 20}


async def test_cursor_walks_all_pages_without_gaps(client, pool):
    await seed(pool, 7)
    seen, cursor = [], None
    for _ in range(5):
        params = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        page = (await client.get("/api/v1/feed", params=params)).json()
        seen += [item["id"] for item in page["data"]]
        cursor = page["page_info"]["next_cursor"]
        if not page["page_info"]["has_more"]:
            break
    assert len(seen) == 7 and len(set(seen)) == 7
    assert cursor is None


async def test_identical_timestamps_do_not_lose_rows(client, pool):
    sid = await pool.fetchval("SELECT id FROM sources WHERE slug = 'cnbc-investing'")
    await store_articles(pool, [normalize(
        RawArticle(title=f"Same second story {char}{char}{char}", url=f"https://x.example/{char}", published_at=NOW),
        source_id=sid, default_category="macro", now=NOW) for char in "abcdefg"], get_settings())
    first = (await client.get("/api/v1/feed", params={"limit": 4})).json()
    second = (await client.get("/api/v1/feed", params={"limit": 4, "cursor": first["page_info"]["next_cursor"]})).json()
    ids = [item["id"] for item in first["data"] + second["data"]]
    assert len(ids) == len(set(ids)) == await pool.fetchval(
        "SELECT count(*) FROM articles WHERE duplicate_of IS NULL")


async def test_new_articles_do_not_shift_existing_cursor(client, pool):
    await seed(pool, 4)
    first = (await client.get("/api/v1/feed", params={"limit": 2})).json()
    await seed(pool, 3, start=NOW + timedelta(hours=1))
    await bump_feed_version(app.state.redis)
    second = (await client.get("/api/v1/feed", params={"limit": 2, "cursor": first["page_info"]["next_cursor"]})).json()
    assert {i["id"] for i in first["data"]}.isdisjoint(i["id"] for i in second["data"])
    assert len(second["data"]) == 2


async def test_category_ticker_and_scope_filters(client, pool):
    await seed(pool, 2, category="crypto", title="Coin", tickers=("BTC",))
    await seed(pool, 3, category="macro", title="Macro")
    assert len((await client.get("/api/v1/feed", params={"category": "crypto"})).json()["data"]) == 2
    assert len((await client.get("/api/v1/feed", params={"ticker": "btc"})).json()["data"]) == 2
    both = await client.get("/api/v1/feed", params={"category": "macro", "ticker": "BTC"})
    assert both.json()["data"] == []
    # crypto non fa parte di Top News nel seed.
    top = (await client.get("/api/v1/feed", params={"scope": "top"})).json()["data"]
    assert {item["category"] for item in top} == {"macro"}


async def test_match_any_returns_ticker_or_category(client, pool):
    await seed(pool, 2, category="crypto", title="Coin", tickers=("BTC",))
    await seed(pool, 2, category="etf", title="Fund")
    await seed(pool, 2, category="macro", title="Other")
    params = {"ticker": "BTC", "category": "etf", "match": "any"}
    data = (await client.get("/api/v1/feed", params=params)).json()["data"]
    assert {item["category"] for item in data} == {"crypto", "etf"}
    assert (await client.get("/api/v1/feed", params={**params, "match": "all"})).json()["data"] == []
    assert (await client.get("/api/v1/feed", params={"match": "nope"})).status_code == 422


async def test_duplicates_are_hidden(client, pool):
    sid = await pool.fetchval("SELECT id FROM sources WHERE slug = 'cnbc-investing'")
    await store_articles(pool, [normalize(
        RawArticle(title="Same headline", url=f"https://x.example/{i}", published_at=NOW),
        source_id=sid, default_category="macro", now=NOW) for i in range(3)], get_settings())
    assert len((await client.get("/api/v1/feed")).json()["data"]) == 1


@pytest.mark.parametrize("cursor", ["garbage", "e30", "eyJ0IjoieCIsImkiOiJ5In0"])
async def test_invalid_cursor_is_400(client, cursor):
    response = await client.get("/api/v1/feed", params={"cursor": cursor})
    assert response.status_code == 400


async def test_limit_is_bounded(client):
    assert (await client.get("/api/v1/feed", params={"limit": 51})).status_code == 422


async def test_cache_hit_invalidation_and_etag(client, pool):
    await seed(pool, 1)
    first = await client.get("/api/v1/feed")
    assert first.headers["X-Cache"] == "miss"
    second = await client.get("/api/v1/feed")
    assert second.headers["X-Cache"] == "hit" and second.content == first.content

    conditional = await client.get("/api/v1/feed", headers={"If-None-Match": first.headers["ETag"]})
    assert conditional.status_code == 304 and conditional.content == b""

    await seed(pool, 1)
    assert (await client.get("/api/v1/feed")).headers["X-Cache"] == "hit"   # non ancora invalidata
    await bump_feed_version(app.state.redis)
    refreshed = await client.get("/api/v1/feed")
    assert refreshed.headers["X-Cache"] == "miss" and len(refreshed.json()["data"]) == 2


async def test_api_survives_redis_outage(client, pool, monkeypatch):
    await seed(pool, 2)

    async def down(*args, **kwargs):
        raise RedisConnectionError("down")
    monkeypatch.setattr(app.state.redis, "get", down)
    monkeypatch.setattr(app.state.redis, "pipeline", lambda **_: (_ for _ in ()).throw(RedisConnectionError("down")))
    response = await client.get("/api/v1/feed")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "bypass" and len(response.json()["data"]) == 2


async def test_stale_copy_served_when_database_fails(client, pool, monkeypatch):
    await seed(pool, 1)
    app.state.settings = app.state.settings.model_copy(update={"feed_cache_ttl_s": 0})
    good = await client.get("/api/v1/feed")

    async def broken(*args, **kwargs):
        raise OSError("db down")
    monkeypatch.setattr("app.repository.fetch_feed", broken)
    response = await client.get("/api/v1/feed")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "stale" and response.content == good.content


async def test_inbound_rate_limit_returns_429(client):
    app.state.settings = app.state.settings.model_copy(update={"api_rate_per_minute": 2})
    codes = [(await client.get("/api/v1/feed")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


async def test_spoofed_forwarded_for_does_not_evade_limit(client):
    app.state.settings = app.state.settings.model_copy(update={"api_rate_per_minute": 1})
    await client.get("/api/v1/feed", headers={"X-Forwarded-For": "1.1.1.1"})
    second = await client.get("/api/v1/feed", headers={"X-Forwarded-For": "2.2.2.2"})
    assert second.status_code == 429


async def test_watchlist_requires_valid_token(client):
    user = uuid4()
    assert (await client.get("/api/v1/me/watchlist")).status_code == 401
    assert (await client.get("/api/v1/me/watchlist", headers=token(user, expired=True))).status_code == 401
    assert (await client.get("/api/v1/me/watchlist", headers=token(user, audience="other"))).status_code == 401
    forged = token(user, secret="another-secret-with-at-least-32-bytes")
    assert (await client.get("/api/v1/me/watchlist", headers=forged)).status_code == 401


async def test_unsigned_token_is_rejected(client):
    unsigned = jwt.encode({"sub": str(uuid4()), "aud": "authenticated", "exp": int(time.time()) + 600},
                          key="", algorithm="none")
    response = await client.get("/api/v1/me/watchlist", headers={"Authorization": f"Bearer {unsigned}"})
    assert response.status_code == 401


async def test_watchlist_feed_end_to_end(client, pool):
    await seed(pool, 2, category="crypto", title="Coin", tickers=("BTC",))
    await seed(pool, 2, category="etf", title="Fund")
    await seed(pool, 2, category="macro", title="Other")
    user = uuid4()
    headers = token(user)

    empty = (await client.get("/api/v1/feed/watchlist", headers=headers)).json()
    assert empty["data"] == [] and empty["page_info"]["has_more"] is False

    saved = await client.put("/api/v1/me/watchlist", headers=headers,
                             json={"tickers": ["btc", "BTC"], "categories": ["etf"]})
    assert saved.json() == {"tickers": ["BTC"], "categories": ["etf"]}

    feed = (await client.get("/api/v1/feed/watchlist", headers=headers)).json()["data"]
    assert {item["category"] for item in feed} == {"crypto", "etf"} and len(feed) == 4

    # Un secondo utente non vede la watchlist del primo.
    assert (await client.get("/api/v1/me/watchlist", headers=token(uuid4()))).json()["tickers"] == []


@pytest.mark.parametrize("body", [{"categories": ["nope"]}, {"tickers": ["BAD TICKER"]}, {"tickers": ["DROP;--"]}])
async def test_watchlist_rejects_bad_input(client, body):
    response = await client.put("/api/v1/me/watchlist", headers=token(uuid4()), json=body)
    assert response.status_code == 422


async def test_bookmarks_lifecycle(client, pool):
    await seed(pool, 1)
    article_id = (await client.get("/api/v1/feed")).json()["data"][0]["id"]
    headers = token(uuid4())
    for _ in range(2):  # idempotente
        assert (await client.put(f"/api/v1/me/bookmarks/{article_id}", headers=headers)).status_code == 204
    assert [a["id"] for a in (await client.get("/api/v1/me/bookmarks", headers=headers)).json()] == [article_id]
    assert (await client.delete(f"/api/v1/me/bookmarks/{article_id}", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/me/bookmarks", headers=headers)).json() == []
    assert (await client.put(f"/api/v1/me/bookmarks/{uuid4()}", headers=headers)).status_code == 404


async def test_calendar_uses_client_timezone_for_day_boundaries(client, pool):
    sid = await pool.fetchval("SELECT id FROM sources WHERE slug = 'ff-calendar'")
    # 23:30 UTC del 5 novembre e' gia' il 6 novembre a Roma.
    await pool.execute(
        """INSERT INTO economic_events (source_id, title, country, starts_at, impact)
           VALUES ($1, 'Late event', 'USD', '2026-11-05T23:30:00Z', 'high')""", sid)
    rome_5 = await client.get("/api/v1/calendar", params={"date": "2026-11-05", "tz": "Europe/Rome"})
    rome_6 = await client.get("/api/v1/calendar", params={"date": "2026-11-06", "tz": "Europe/Rome"})
    assert rome_5.json()["data"] == []
    assert rome_6.json()["data"][0]["title"] == "Late event"
    assert (await client.get("/api/v1/calendar", params={"tz": "Not/AZone"})).status_code == 400


async def test_token_bucket_blocks_after_burst(redis):
    bucket = TokenBucket(redis, "test", rate_per_minute=60)  # capacita' 10, 1 token/s
    for _ in range(10):
        await bucket.acquire()
    started = time.monotonic()
    await bucket.acquire()
    assert time.monotonic() - started >= 0.5


async def test_token_bucket_penalty_pauses_all_replicas(redis):
    bucket = TokenBucket(redis, "penalty", rate_per_minute=6000)
    await bucket.penalize(0.05)
    started = time.monotonic()
    await bucket.acquire()
    assert time.monotonic() - started >= 0.04


async def test_allow_request_counts_per_client(redis):
    assert await allow_request(redis, "a", 1) and not await allow_request(redis, "a", 1)
    assert await allow_request(redis, "b", 1)
