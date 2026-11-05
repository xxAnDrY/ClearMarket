"""Query di lettura dell'API."""
import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg


class InvalidCursor(ValueError):
    pass


def encode_cursor(published_at: datetime, article_id: UUID) -> str:
    raw = json.dumps({"t": published_at.isoformat(), "i": str(article_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Il cursore e' opaco per il client, ma resta input non fidato."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        published_at = datetime.fromisoformat(data["t"])
        if published_at.tzinfo is None:
            raise ValueError("naive timestamp")
        return published_at, UUID(data["i"])
    except (binascii.Error, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise InvalidCursor(cursor) from exc


@dataclass(frozen=True, slots=True)
class FeedFilter:
    categories: tuple[str, ...] = ()
    tickers: tuple[str, ...] = ()
    # True (watchlist): basta una delle due condizioni. False (query esplicita): entrambe.
    match_any: bool = False
    search: str | None = None


async def fetch_feed(
    pool: asyncpg.Pool, feed_filter: FeedFilter, limit: int, cursor: str | None,
) -> dict[str, Any]:
    conditions = ["a.visible"]
    params: list[Any] = []

    def bind(value: Any) -> str:
        params.append(value)
        return f"${len(params)}"

    filters = []
    if feed_filter.categories:
        filters.append(f"a.category = ANY({bind(list(feed_filter.categories))})")
    if feed_filter.tickers:
        filters.append(f"a.related_tickers && {bind(list(feed_filter.tickers))}::text[]")
    if filters:
        joiner = " OR " if feed_filter.match_any else " AND "
        conditions.append(f"({joiner.join(filters)})")

    if feed_filter.search:
        escaped = re.sub(r"([\\%_])", r"\\\1", feed_filter.search)
        term = bind(f"%{escaped}%")
        conditions.append(f"(a.title ILIKE {term} OR a.summary ILIKE {term} "
                          f"OR {bind(feed_filter.search.upper())} = ANY(a.related_tickers))")

    if cursor:
        published_at, article_id = decode_cursor(cursor)
        # Keyset: confronto di riga sulla stessa tupla dell'ORDER BY. A differenza
        # di OFFSET, le notizie nuove in testa non spostano le pagine successive.
        conditions.append(
            f"(a.published_at, a.id) < ({bind(published_at)}::timestamptz, {bind(article_id)}::uuid)")

    # Una riga in piu' dice se esiste una pagina successiva senza fare COUNT(*).
    query = f"""
        SELECT a.id, a.title, a.summary, a.source_url, a.published_at, a.category,
               a.related_tickers, a.sentiment::text AS sentiment, a.sentiment_score,
               a.translation_status, s.slug AS source_slug, s.name AS source_name
        FROM articles a JOIN sources s ON s.id = a.source_id
        WHERE {' AND '.join(conditions)}
        ORDER BY a.published_at DESC, a.id DESC
        LIMIT {bind(limit + 1)}
    """
    rows = await pool.fetch(query, *params)
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "data": [_article(row) for row in page],
        "page_info": {
            "next_cursor": encode_cursor(page[-1]["published_at"], page[-1]["id"]) if has_more else None,
            "has_more": has_more,
            "limit": limit,
        },
    }


def _article(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "summary": row["summary"],
        "source": {"slug": row["source_slug"], "name": row["source_name"]},
        "source_url": row["source_url"],
        "translated": row["translation_status"] == "done",
        "published_at": row["published_at"].isoformat(),
        "category": row["category"],
        "related_tickers": row["related_tickers"],
        "sentiment": {"label": row["sentiment"], "score": row["sentiment_score"]},
    }


async def top_news_categories(pool: asyncpg.Pool) -> tuple[str, ...]:
    rows = await pool.fetch("SELECT slug FROM categories WHERE in_top_news ORDER BY sort_order")
    return tuple(row["slug"] for row in rows)


async def get_watchlist(pool: asyncpg.Pool, user_id: UUID) -> dict[str, list[str]]:
    rows = await pool.fetch(
        "SELECT ticker, category FROM user_watchlist WHERE user_id = $1 ORDER BY created_at, id",
        user_id)
    return {
        "tickers": [row["ticker"] for row in rows if row["ticker"]],
        "categories": [row["category"] for row in rows if row["category"]],
    }


async def replace_watchlist(
    pool: asyncpg.Pool, user_id: UUID, tickers: list[str], categories: list[str],
) -> None:
    """PUT idempotente: il client invia sempre lo stato completo."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM user_watchlist WHERE user_id = $1", user_id)
        await conn.executemany(
            "INSERT INTO user_watchlist (user_id, ticker, category) VALUES ($1, $2, $3)",
            [(user_id, ticker, None) for ticker in tickers]
            + [(user_id, None, category) for category in categories])


async def fetch_bookmarks(pool: asyncpg.Pool, user_id: UUID, limit: int) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """SELECT a.id, a.title, a.summary, a.source_url, a.published_at, a.category,
                  a.related_tickers, a.sentiment::text AS sentiment, a.sentiment_score,
                  a.translation_status, s.slug AS source_slug, s.name AS source_name
           FROM user_bookmarks b
           JOIN articles a ON a.id = b.article_id
           JOIN sources s ON s.id = a.source_id
           WHERE b.user_id = $1
           ORDER BY b.created_at DESC
           LIMIT $2""", user_id, limit)
    return [_article(row) for row in rows]


async def fetch_events(
    pool: asyncpg.Pool, start: datetime, end: datetime, countries: list[str],
    impacts: list[str],
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """SELECT id, title, country, starts_at, impact::text AS impact, forecast, previous, actual
           FROM economic_events
           WHERE starts_at >= $1 AND starts_at < $2
             AND (cardinality($3::text[]) = 0 OR country = ANY($3::text[]))
             AND (cardinality($4::text[]) = 0 OR impact::text = ANY($4::text[]))
           ORDER BY starts_at, impact DESC, title""", start, end, countries, impacts)
    return [{**dict(row), "id": str(row["id"]), "starts_at": row["starts_at"].isoformat()}
            for row in rows]
