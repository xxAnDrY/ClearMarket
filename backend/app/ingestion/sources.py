"""Adapter delle fonti: scaricano e traducono, senza toccare DB o logica di dominio."""
import asyncio
import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx

from app.ingestion.normalize import RawArticle
from app.ratelimit import TokenBucket

log = logging.getLogger(__name__)

MAX_FEED_BYTES = 5 * 1024 * 1024


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
    provider_cursor: str | None = None
    not_modified: bool = False


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        header = response.headers.get("Retry-After", "")
        raise RateLimited(float(header) if header.isdigit() else 60.0)
    response.raise_for_status()


async def _conditional_get(client: httpx.AsyncClient, source: dict[str, Any]) -> httpx.Response:
    headers = {}
    if source["http_etag"]:
        headers["If-None-Match"] = source["http_etag"]
    if source["http_last_modified"]:
        headers["If-Modified-Since"] = source["http_last_modified"]
    return await client.get(source["url"], headers=headers, follow_redirects=True)


async def fetch_rss(client: httpx.AsyncClient, source: dict[str, Any]) -> FetchResult:
    response = await _conditional_get(client, source)
    if response.status_code == 304:
        return FetchResult(not_modified=True, etag=source["http_etag"],
                           last_modified=source["http_last_modified"])
    _raise_for_status(response)
    if len(response.content) > MAX_FEED_BYTES:
        raise ValueError(f"feed too large: {len(response.content)} bytes")

    # feedparser e' sincrono e CPU-bound: fuori dall'event loop.
    parsed = await asyncio.to_thread(feedparser.parse, response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"unparsable feed: {parsed.bozo_exception!r}")

    articles = []
    for entry in parsed.entries:
        # I *_parsed di feedparser sono struct_time gia' convertiti in UTC.
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        articles.append(RawArticle(
            title=entry.get("title", ""),
            url=entry.get("link", ""),
            summary=entry.get("summary", ""),
            published_at=(datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc)
                          if stamp else None),
        ))
    return FetchResult(articles=articles, etag=response.headers.get("ETag"),
                       last_modified=response.headers.get("Last-Modified"))


def _finnhub_item(item: dict[str, Any]) -> RawArticle:
    related = item.get("related") or ""
    stamp = item.get("datetime")
    return RawArticle(
        title=item.get("headline", ""),
        url=item.get("url", ""),
        summary=item.get("summary", ""),
        published_at=datetime.fromtimestamp(stamp, timezone.utc) if stamp else None,
        tickers=tuple(symbol.strip() for symbol in related.split(",") if symbol.strip()),
    )


async def fetch_finnhub_news(
    client: httpx.AsyncClient, source: dict[str, Any], bucket: TokenBucket, api_key: str,
) -> FetchResult:
    # minId: Finnhub restituisce solo gli id successivi all'ultimo gia' visto.
    params: dict[str, str] = {}
    if source["provider_cursor"]:
        params["minId"] = source["provider_cursor"]
    await bucket.acquire()
    # Il token va in header: nei log di httpx finirebbe l'URL completa.
    # copy_merge_params: `params=` di httpx sostituirebbe il ?category= gia' nell'URL.
    url = httpx.URL(source["url"]).copy_merge_params(params)
    response = await client.get(url, headers={"X-Finnhub-Token": api_key})
    if response.status_code == 429:
        await bucket.penalize(60)
    _raise_for_status(response)
    items = response.json()
    newest = max((int(item["id"]) for item in items if item.get("id")), default=None)
    return FetchResult(articles=[_finnhub_item(item) for item in items],
                       provider_cursor=str(newest) if newest else source["provider_cursor"])


async def fetch_finnhub_company(
    client: httpx.AsyncClient, source: dict[str, Any], bucket: TokenBucket, api_key: str,
    symbols: list[str], today: date | None = None,
) -> FetchResult:
    """News per ticker delle watchlist. Un errore su un simbolo non blocca gli altri."""
    today = today or datetime.now(timezone.utc).date()
    articles: list[RawArticle] = []
    for symbol in symbols:
        await bucket.acquire()
        response = await client.get(
            source["url"],
            params={"symbol": symbol, "from": (today - timedelta(days=2)).isoformat(),
                    "to": today.isoformat()},
            headers={"X-Finnhub-Token": api_key},
        )
        if response.status_code == 429:
            await bucket.penalize(60)
            if articles:  # conserva il lavoro fatto, il prossimo ciclo riprende
                break
        if response.status_code == 403:
            # Simbolo fuori dal piano (es. listini UE sul free tier): atteso, non un guasto.
            log.info("finnhub: symbol %s not available on this plan", symbol)
            continue
        _raise_for_status(response)
        for item in response.json():
            raw = _finnhub_item(item)
            raw.tickers = tuple(dict.fromkeys((symbol, *raw.tickers)))
            articles.append(raw)
    return FetchResult(articles=articles)


_FF_IMPACT = {"low": "low", "medium": "medium", "high": "high", "holiday": "holiday"}


async def fetch_ff_calendar(client: httpx.AsyncClient, source: dict[str, Any]) -> FetchResult:
    response = await _conditional_get(client, source)
    if response.status_code == 304:
        return FetchResult(not_modified=True, etag=source["http_etag"],
                           last_modified=source["http_last_modified"])
    _raise_for_status(response)
    events = []
    for item in response.json():
        try:
            events.append({
                "title": item["title"].strip(),
                "country": item["country"].strip().upper(),
                "starts_at": datetime.fromisoformat(item["date"]).astimezone(timezone.utc),
                "impact": _FF_IMPACT.get(str(item.get("impact", "")).lower(), "low"),
                "forecast": item.get("forecast") or None,
                "previous": item.get("previous") or None,
                "actual": item.get("actual") or None,
            })
        except (KeyError, ValueError, AttributeError) as exc:
            log.warning("skipping malformed calendar event: %r (%s)", item, exc)
    return FetchResult(events=events, etag=response.headers.get("ETag"),
                       last_modified=response.headers.get("Last-Modified"))
