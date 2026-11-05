"""Adapter delle fonti: scaricano e traducono il formato, senza toccare lo stato globale."""
import asyncio
import calendar
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

from clearmarket.catalog import Source
from clearmarket.normalize import RawArticle

log = logging.getLogger(__name__)

MAX_FEED_BYTES = 5 * 1024 * 1024
_IMPACTS = {"low", "medium", "high", "holiday"}


class RateLimited(Exception):
    def __init__(self, retry_after_s: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after_s}s")
        self.retry_after_s = retry_after_s


@dataclass(slots=True)
class FetchResult:
    articles: list[RawArticle] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    cursor: str | None = None
    not_modified: bool = False


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        header = response.headers.get("Retry-After", "")
        raise RateLimited(float(header) if header.isdigit() else 900.0)
    response.raise_for_status()


async def _conditional_get(client: httpx.AsyncClient, source: Source, memo: dict[str, Any]) -> httpx.Response:
    headers = {}
    if memo.get("etag"):
        headers["If-None-Match"] = memo["etag"]
    if memo.get("last_modified"):
        headers["If-Modified-Since"] = memo["last_modified"]
    return await client.get(source.url, headers=headers, follow_redirects=True)


def _unchanged(memo: dict[str, Any]) -> FetchResult:
    return FetchResult(not_modified=True, etag=memo.get("etag"), last_modified=memo.get("last_modified"))


async def fetch_rss(client: httpx.AsyncClient, source: Source, memo: dict[str, Any]) -> FetchResult:
    response = await _conditional_get(client, source, memo)
    if response.status_code == 304:
        return _unchanged(memo)
    _raise_for_status(response)
    if len(response.content) > MAX_FEED_BYTES:
        raise ValueError(f"feed too large: {len(response.content)} bytes")

    parsed = await asyncio.to_thread(feedparser.parse, response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"unparsable feed: {parsed.bozo_exception!r}")

    articles = []
    for entry in parsed.entries:
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        articles.append(RawArticle(
            title=entry.get("title", ""),
            url=entry.get("link", ""),
            summary=entry.get("summary", ""),
            published_at=(datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc) if stamp else None),
        ))
    return FetchResult(articles=articles, etag=response.headers.get("ETag"),
                       last_modified=response.headers.get("Last-Modified"))


async def fetch_finnhub(client: httpx.AsyncClient, source: Source, memo: dict[str, Any], api_key: str) -> FetchResult:
    params = {"minId": memo["cursor"]} if memo.get("cursor") else {}
    # copy_merge_params: `params=` di httpx sostituirebbe il ?category= gia' nell'URL.
    url = httpx.URL(source.url).copy_merge_params(params)
    # Il token va in header: nell'URL finirebbe nei log.
    response = await client.get(url, headers={"X-Finnhub-Token": api_key})
    _raise_for_status(response)
    items = response.json()
    articles = []
    for item in items:
        stamp = item.get("datetime")
        related = item.get("related") or ""
        articles.append(RawArticle(
            title=item.get("headline", ""),
            url=item.get("url", ""),
            summary=item.get("summary", ""),
            published_at=datetime.fromtimestamp(stamp, timezone.utc) if stamp else None,
            tickers=tuple(symbol.strip() for symbol in related.split(",") if symbol.strip()),
        ))
    newest = max((int(item["id"]) for item in items if item.get("id")), default=None)
    return FetchResult(articles=articles, cursor=str(newest) if newest else memo.get("cursor"))


async def fetch_calendar(client: httpx.AsyncClient, source: Source, memo: dict[str, Any]) -> FetchResult:
    response = await _conditional_get(client, source, memo)
    if response.status_code == 304:
        return _unchanged(memo)
    _raise_for_status(response)
    events = []
    for item in response.json():
        try:
            impact = str(item.get("impact", "")).lower()
            events.append({
                "title": item["title"].strip(),
                "country": item["country"].strip().upper(),
                "starts_at": datetime.fromisoformat(item["date"]).astimezone(timezone.utc).isoformat(),
                "impact": impact if impact in _IMPACTS else "low",
                "forecast": item.get("forecast") or None,
                "previous": item.get("previous") or None,
                "actual": item.get("actual") or None,
            })
        except (KeyError, ValueError, AttributeError) as exc:
            log.warning("skipping malformed calendar event: %r (%s)", item, exc)
    return FetchResult(events=events, etag=response.headers.get("ETag"),
                       last_modified=response.headers.get("Last-Modified"))
