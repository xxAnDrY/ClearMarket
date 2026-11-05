"""Worker di ingestion. Avvio: `python -m app.ingestion.worker`.

Ogni tick reclama le fonti scadute, le scarica in parallelo (con limite), normalizza,
deduplica e salva. Piu' repliche sono sicure: il claim usa FOR UPDATE SKIP LOCKED e il
budget verso i provider e' condiviso su Redis.
"""
import asyncio
import logging
import random
import signal
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.cache import bump_feed_version
from app.config import Settings, get_settings
from app.db import create_pool
from app.ingestion.dedupe import title_signature
from app.ingestion.markets import refresh_quotes, refresh_spread
from app.ingestion.normalize import NormalizedArticle, normalize
from app.ingestion.schedule import next_poll_delay
from app.ingestion.sources import (
    FetchResult,
    RateLimited,
    fetch_ff_calendar,
    fetch_finnhub_company,
    fetch_finnhub_news,
    fetch_rss,
)
from app.ingestion.translate import TranslationQueue, build_backends
from app.ratelimit import TokenBucket

log = logging.getLogger("clearmarket.worker")

MAX_BACKOFF_S = 3600

# Il lease sposta next_poll_at in avanti: se il worker muore, la fonte torna
# disponibile da sola alla scadenza.
_CLAIM_SQL = """
UPDATE sources SET next_poll_at = now() + make_interval(secs => $2)
WHERE id IN (
    SELECT id FROM sources
    WHERE enabled AND next_poll_at <= now()
    ORDER BY next_poll_at
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, slug, kind::text AS kind, url, default_category, language, poll_interval_s,
          closed_poll_interval_s, consecutive_failures, http_etag, http_last_modified, provider_cursor
"""

# L1: ON CONFLICT scarta la stessa URL.
# L2: stesso title_hash entro 48 ore, l'articolo piu' vecchio e' il canonico.
# L3: titolo simile entro la finestra, poi filtrato in Python sulla firma del titolo.
_FIND_CANONICAL_SQL = """
SELECT id FROM articles
WHERE duplicate_of IS NULL
  AND published_at BETWEEN $2::timestamptz - interval '48 hours'
                       AND $2::timestamptz + interval '48 hours'
  AND title_hash = $1
ORDER BY published_at
LIMIT 1
"""

_FIND_NEAR_SQL = """
SELECT id, title_original FROM articles
WHERE duplicate_of IS NULL
  AND published_at BETWEEN $2::timestamptz - make_interval(hours => $4)
                       AND $2::timestamptz + make_interval(hours => $4)
  AND similarity(title_original, $1) >= $3
ORDER BY similarity(title_original, $1) DESC
LIMIT 5
"""

_INSERT_SQL = """
INSERT INTO articles (source_id, category, title, summary, source_url, published_at,
                      related_tickers, sentiment, sentiment_score, url_hash, title_hash,
                      duplicate_of, language, title_original, summary_original,
                      translation_status)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8::sentiment_label, $9, $10, $11, $12, $13, $14, $15, $16)
ON CONFLICT (url_hash) DO NOTHING
RETURNING id
"""

_UPSERT_EVENT_SQL = """
INSERT INTO economic_events (source_id, title, country, starts_at, impact, forecast, previous, actual)
VALUES ($1, $2, $3, $4, $5::event_impact, $6, $7, $8)
ON CONFLICT (title, country, starts_at) DO UPDATE
SET impact = EXCLUDED.impact, forecast = EXCLUDED.forecast, previous = EXCLUDED.previous,
    actual = COALESCE(EXCLUDED.actual, economic_events.actual), updated_at = now()
"""


async def find_canonical(
    conn: asyncpg.Connection, article: NormalizedArticle, settings: Settings,
) -> Any | None:
    exact = await conn.fetchval(_FIND_CANONICAL_SQL, article.title_hash, article.published_at)
    if exact:
        return exact
    candidates = await conn.fetch(_FIND_NEAR_SQL, article.title_original, article.published_at,
                                  settings.near_dup_threshold, settings.near_dup_window_hours)
    signature = title_signature(article.title_original)
    for row in candidates:
        if title_signature(row["title_original"]) == signature:
            return row["id"]
    return None


async def store_articles(
    pool: asyncpg.Pool, articles: list[NormalizedArticle], settings: Settings,
) -> int:
    """Salva il batch e restituisce quanti articoli sono visibili nel feed."""
    visible = 0
    async with pool.acquire() as conn:
        # Prefiltro: la maggior parte degli item di un feed e' gia' nota, e gli
        # controlli di L2/L3 costano piu' di un lookup sull'hash.
        known = {row["url_hash"] for row in await conn.fetch(
            "SELECT url_hash FROM articles WHERE url_hash = ANY($1)",
            [article.url_hash for article in articles])}
        seen = set(known)
        for article in articles:
            if article.url_hash in seen:
                continue
            seen.add(article.url_hash)
            canonical = await find_canonical(conn, article, settings)
            inserted = await conn.fetchval(
                _INSERT_SQL, article.source_id, article.category, article.title, article.summary,
                article.url, article.published_at, article.related_tickers, article.sentiment,
                article.sentiment_score, article.url_hash, article.title_hash, canonical,
                article.language, article.title_original, article.summary_original,
                article.translation_status)
            if inserted and canonical is None and article.translation_status == "not_needed":
                visible += 1
    return visible


async def watched_symbols(pool: asyncpg.Pool, offset: int, limit: int) -> list[str]:
    """Pagina circolare sui ticker piu' seguiti: ogni ciclo avanza nella coda."""
    symbols = await pool.fetch(
        """SELECT ticker FROM user_watchlist WHERE ticker IS NOT NULL
           GROUP BY ticker ORDER BY count(*) DESC, ticker""")
    names = [row["ticker"] for row in symbols]
    if len(names) <= limit:
        return names
    start = offset % len(names)
    return (names + names)[start:start + limit]


class Worker:
    def __init__(self, settings: Settings, pool: asyncpg.Pool, redis: Redis,
                 client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.pool = pool
        self.redis = redis
        self.client = client
        self.finnhub_bucket = TokenBucket(redis, "finnhub", settings.finnhub_rate_per_minute)
        self.translations = TranslationQueue(pool, build_backends(settings, client),
                                             settings.translate_batch)
        self._stop = asyncio.Event()
        self._next_market_refresh = 0.0

    def stop(self) -> None:
        self._stop.set()

    async def _fetch(self, source: dict[str, Any]) -> FetchResult:
        kind = source["kind"]
        if kind == "rss":
            return await fetch_rss(self.client, source)
        if kind == "ff_calendar":
            return await fetch_ff_calendar(self.client, source)

        api_key = self.settings.finnhub_api_key
        if not api_key:
            raise RuntimeError("FINNHUB_API_KEY is not configured")
        if kind == "finnhub_news":
            return await fetch_finnhub_news(self.client, source, self.finnhub_bucket, api_key)
        if kind == "finnhub_company":
            batch = self.settings.finnhub_company_batch
            # La posizione nella coda vive in provider_cursor.
            offset = int(source["provider_cursor"] or 0)
            symbols = await watched_symbols(self.pool, offset, batch)
            result = await fetch_finnhub_company(
                self.client, source, self.finnhub_bucket, api_key, symbols)
            result.provider_cursor = str(offset + len(symbols))
            return result
        raise ValueError(f"unknown source kind: {kind}")

    async def process(self, source: dict[str, Any]) -> None:
        try:
            result = await self._fetch(source)
            new_visible = await self._persist(source, result)
        except RateLimited as exc:
            log.warning("%s: %s", source["slug"], exc)
            await self._reschedule(source, delay_s=exc.retry_after_s, error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - i guasti di una fonte restano isolati
            failures = source["consecutive_failures"] + 1
            delay = min(source["poll_interval_s"] * 2 ** failures, MAX_BACKOFF_S)
            log.warning("%s failed (%d in a row): %r", source["slug"], failures, exc)
            await self._reschedule(source, delay_s=delay, error=repr(exc)[:500], failures=failures)
            return

        await self.pool.execute(
            """UPDATE sources SET next_poll_at = now() + make_interval(secs => $2),
                   consecutive_failures = 0, last_success_at = now(), last_error = NULL,
                   http_etag = $3, http_last_modified = $4, provider_cursor = $5
               WHERE id = $1""",
            source["id"],
            self._jittered(next_poll_delay(datetime.now(timezone.utc), source["poll_interval_s"],
                                           source["closed_poll_interval_s"])),
            result.etag, result.last_modified, result.provider_cursor)
        if new_visible:
            await self._invalidate_cache()
        log.info("%s: %d fetched, %d new%s", source["slug"],
                 len(result.articles) + len(result.events), new_visible,
                 " (304)" if result.not_modified else "")

    async def _persist(self, source: dict[str, Any], result: FetchResult) -> int:
        if result.events:
            await self.pool.executemany(_UPSERT_EVENT_SQL, [
                (source["id"], event["title"], event["country"], event["starts_at"], event["impact"],
                 event["forecast"], event["previous"], event["actual"])
                for event in result.events])
        # BCE e Fed parlano sempre di politica monetaria, ma le loro press release
        # sulla vigilanza non contengono parole chiave utili: la fonte decide.
        lock_category = source["default_category"] == "monetary_policy"
        now = datetime.now(timezone.utc)
        normalized = [article for raw in result.articles if (article := normalize(
            raw, source_id=source["id"], default_category=source["default_category"],
            lock_category=lock_category, language=source["language"], now=now))]
        return await store_articles(self.pool, normalized, self.settings) if normalized else 0

    @staticmethod
    def _jittered(seconds: float) -> float:
        # Fonti con lo stesso intervallo non devono restare in fase per sempre.
        return seconds * random.uniform(0.9, 1.1)

    async def _reschedule(self, source: dict[str, Any], *, delay_s: float, error: str,
                          failures: int | None = None) -> None:
        await self.pool.execute(
            """UPDATE sources SET next_poll_at = now() + make_interval(secs => $2),
                   consecutive_failures = COALESCE($3, consecutive_failures), last_error = $4
               WHERE id = $1""",
            source["id"], float(self._jittered(delay_s)), failures, error)

    async def _invalidate_cache(self) -> None:
        try:
            await bump_feed_version(self.redis)
        except (RedisError, OSError) as exc:
            # Il feed resta solo stantio fino alla scadenza del TTL.
            log.warning("cache invalidation failed: %r", exc)

    async def run_once(self) -> int:
        rows = await self.pool.fetch(_CLAIM_SQL, self.settings.worker_concurrency,
                                     float(self.settings.worker_lease_s))
        await asyncio.gather(*(self.process(dict(row)) for row in rows))
        return len(rows)

    async def translate_once(self) -> int:
        done = await self.translations.run_once()
        if done:
            await self._invalidate_cache()
        return done

    async def refresh_markets(self) -> int:
        """Quotazioni con la stessa logica oraria delle fonti: 5 minuti, 30 a mercato chiuso."""
        if time.monotonic() < self._next_market_refresh:
            return 0
        delay = next_poll_delay(datetime.now(timezone.utc), 300, 1800)
        self._next_market_refresh = time.monotonic() + delay
        updated = await refresh_quotes(self.pool, self.client)
        await refresh_spread(self.pool)
        return updated

    async def _loop(self, step: Callable[[], Awaitable[int]], tick_s: float) -> None:
        while not self._stop.is_set():
            try:
                await step()
            except Exception as exc:  # noqa: BLE001 - il loop deve sopravvivere ai guasti
                log.exception("tick failed: %r", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), tick_s)
            except TimeoutError:
                pass

    async def run_forever(self) -> None:
        log.info("worker started")
        # Due cicli separati: una traduzione lenta non deve ritardare il polling.
        await asyncio.gather(self._loop(self.run_once, self.settings.worker_tick_s),
                             self._loop(self.translate_once, self.settings.translate_tick_s),
                             self._loop(self.refresh_markets, self.settings.worker_tick_s))
        log.info("worker stopped")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    pool = await create_pool(settings)
    redis = Redis.from_url(settings.redis_url, decode_responses=True,
                           socket_timeout=2, socket_connect_timeout=2)
    headers = {"User-Agent": settings.http_user_agent}
    async with httpx.AsyncClient(timeout=settings.http_timeout_s, headers=headers) as client:
        worker = Worker(settings, pool, redis, client)
        loop = asyncio.get_running_loop()
        for name in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(name, worker.stop)
            except NotImplementedError:  # Windows
                pass
        try:
            await worker.run_forever()
        finally:
            await pool.close()
            await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
