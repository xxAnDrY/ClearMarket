"""Un giro completo: raccoglie, deduplica e scrive i JSON del sito.

Uso: `python -m clearmarkets.run --out <cartella>`
La cartella contiene `state.json` (memoria tra un giro e l'altro) e `public/` (dati del sito).
Non servono database ne' processi sempre attivi: il job programmato la conserva tra i giri.
"""
import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from clearmarkets.catalog import SOURCES, Source
from clearmarkets.dedupe import title_signature, trigram_similarity
from clearmarkets.markets import refresh_quotes, refresh_spread
from clearmarkets.normalize import NormalizedArticle, normalize
from clearmarkets.sources import FetchResult, RateLimited, fetch_finnhub, fetch_rss

log = logging.getLogger("clearmarkets")

STATE_VERSION = 2
RETENTION_DAYS = 14
FEED_LIMIT = 800
QUOTE_MAX_AGE_DAYS = 7
EXACT_WINDOW = timedelta(hours=48)
NEAR_WINDOW = timedelta(hours=12)
NEAR_THRESHOLD = 0.72
USER_AGENT = "ClearMarketsBot/1.0"
CONCURRENCY = 10


def empty_state() -> dict[str, Any]:
    return {"version": STATE_VERSION, "articles": [], "sources": {}, "quotes": {}}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    saved = json.loads(path.read_text(encoding="utf-8"))
    # Uno stato di formato diverso si butta: le fonti lo ricostruiscono in un giro.
    return saved if saved.get("version") == STATE_VERSION else empty_state()


def _time(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def is_visible(article: dict[str, Any]) -> bool:
    return article["duplicate_of"] is None


def find_duplicate(candidate: NormalizedArticle, articles: list[dict[str, Any]]) -> str | None:
    """L2: stesso titolo entro 48 ore. L3: titolo simile entro 12 ore con la stessa firma.

    Il duplicato non si scarta: resta con `duplicate_of`, cosi' non viene ripreso al giro dopo.
    """
    canonical = [article for article in articles if article["duplicate_of"] is None]
    exact = [article for article in canonical
             if article["title_hash"] == candidate.title_hash.hex()
             and abs(_time(article["published_at"]) - candidate.published_at) <= EXACT_WINDOW]
    if exact:
        return min(exact, key=lambda article: article["published_at"])["id"]
    signature = title_signature(candidate.title)
    for article in canonical:
        if (abs(_time(article["published_at"]) - candidate.published_at) <= NEAR_WINDOW
                and trigram_similarity(article["title"], candidate.title) >= NEAR_THRESHOLD
                and title_signature(article["title"]) == signature):
            return article["id"]
    return None


def add_articles(state: dict[str, Any], source: Source, incoming: list[NormalizedArticle], now: datetime) -> int:
    """Salva i nuovi articoli e restituisce quanti ne sono stati aggiunti."""
    known = {article["url_hash"] for article in state["articles"]}
    oldest = now - timedelta(days=RETENTION_DAYS)
    added = 0
    for item in incoming:
        url_hash = item.url_hash.hex()
        if url_hash in known or item.published_at < oldest:
            continue
        known.add(url_hash)
        state["articles"].append({
            "id": url_hash[:20],
            "source_slug": source.slug,
            "source_name": source.name,
            "category": item.category,
            "title": item.title,
            "summary": item.summary,
            "language": item.language,
            "source_url": item.url,
            "published_at": item.published_at.isoformat(),
            "related_tickers": item.related_tickers,
            "sentiment": item.sentiment,
            "sentiment_score": item.sentiment_score,
            "url_hash": url_hash,
            "title_hash": item.title_hash.hex(),
            "duplicate_of": find_duplicate(item, state["articles"]),
        })
        added += 1
    return added


async def _fetch(client: httpx.AsyncClient, source: Source, memo: dict[str, Any], finnhub_key: str | None) -> FetchResult:
    if source.kind == "rss":
        return await fetch_rss(client, source, memo)
    return await fetch_finnhub(client, source, memo, finnhub_key or "")


def _is_due(source: Source, memo: dict[str, Any], now: datetime, finnhub_key: str | None) -> bool:
    if source.kind == "finnhub" and not finnhub_key:
        return False
    return not (memo.get("skip_until") and now < _time(memo["skip_until"]))


async def collect(client: httpx.AsyncClient, state: dict[str, Any], now: datetime, finnhub_key: str | None) -> None:
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(source: Source) -> None:
        memo = state["sources"].setdefault(source.slug, {})
        if not _is_due(source, memo, now, finnhub_key):
            return
        try:
            async with gate:
                result = await _fetch(client, source, memo, finnhub_key)
        except RateLimited as exc:
            memo["skip_until"] = (now + timedelta(seconds=exc.retry_after_s)).isoformat()
            memo["last_error"] = str(exc)
            log.warning("%s: %s", source.slug, exc)
            return
        except Exception as exc:  # noqa: BLE001 - i guasti di una fonte restano isolati
            memo["failures"] = memo.get("failures", 0) + 1
            memo["last_error"] = repr(exc)[:300]
            log.warning("%s failed: %r", source.slug, exc)
            return

        lock_category = source.default_category == "monetary_policy"
        normalized = [article for raw in result.articles if (article := normalize(
            raw, source_slug=source.slug, default_category=source.default_category,
            lock_category=lock_category, language=source.language, now=now))]
        added = add_articles(state, source, normalized, now)
        memo.update(etag=result.etag, last_modified=result.last_modified, cursor=result.cursor,
                    failures=0, last_error=None, skip_until=None, last_success=now.isoformat())
        log.info("%s: %d fetched, %d new", source.slug, len(result.articles), added)

    await asyncio.gather(*(one(source) for source in SOURCES))


def prune(state: dict[str, Any], now: datetime) -> None:
    oldest = now - timedelta(days=RETENTION_DAYS)
    state["articles"] = [item for item in state["articles"] if _time(item["published_at"]) >= oldest]


def _public_article(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": article["id"],
        "title": article["title"],
        "summary": article["summary"],
        "source": {"slug": article["source_slug"], "name": article["source_name"]},
        "source_url": article["source_url"],
        "language": article["language"],
        "published_at": article["published_at"],
        "category": article["category"],
        "related_tickers": article["related_tickers"],
        "sentiment": {"label": article["sentiment"], "score": article["sentiment_score"]},
    }


def public_files(state: dict[str, Any], now: datetime) -> dict[str, dict[str, Any]]:
    generated_at = now.isoformat()
    visible = sorted(filter(is_visible, state["articles"]), key=lambda item: item["published_at"], reverse=True)
    oldest_quote = now - timedelta(days=QUOTE_MAX_AGE_DAYS)
    quotes = [quote for quote in state["quotes"].values() if _time(quote["as_of"]) >= oldest_quote]
    return {
        "feed.json": {"generated_at": generated_at,
                      "articles": [_public_article(item) for item in visible[:FEED_LIMIT]]},
        "markets.json": {"generated_at": generated_at,
                         "quotes": sorted(quotes, key=lambda quote: quote["order"])},
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)  # un giro interrotto non lascia file a meta'


async def run(out: Path, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    state_path = out / "state.json"
    state = load_state(state_path)
    finnhub_key = os.environ.get("FINNHUB_API_KEY") or None

    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": USER_AGENT}) as client:
        await collect(client, state, now, finnhub_key)
        await refresh_quotes(client, state["quotes"])
    refresh_spread(state["articles"], state["quotes"])
    prune(state, now)

    write_json(state_path, state)
    for name, data in public_files(state, now).items():
        write_json(out / "public" / name, data)
    log.info("done: %d articles", len(state["articles"]))
    return state


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    asyncio.run(run(parser.parse_args().out))


if __name__ == "__main__":
    main()
