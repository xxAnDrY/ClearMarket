"""API FastAPI. Avvio: `uvicorn app.main:app`."""
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg
import jwt
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app import repository as repo
from app.auth import CurrentUser
from app.cache import cached_json
from app.config import get_settings
from app.db import create_pool
from app.ingestion.markets import fetch_markets
from app.ingestion.schedule import is_market_open
from app.ratelimit import allow_request
from app.schemas import (
    ArticleOut,
    CalendarResponse,
    CategoryOut,
    FeedResponse,
    Watchlist,
)

MAX_PAGE_SIZE = 50
MAX_FILTER_VALUES = 50


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    if not hasattr(app.state, "pool"):  # i test iniettano pool e redis
        app.state.pool = await create_pool(settings)
        app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True,
                                         socket_timeout=0.25, socket_connect_timeout=0.25)
    app.state.jwks = jwt.PyJWKClient(settings.jwt_jwks_url) if settings.jwt_jwks_url else None
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Cache = Annotated[Redis, Depends(get_redis)]


def client_ip(request: Request) -> str:
    hops = request.app.state.settings.trusted_proxy_hops
    if hops > 0:
        # L'indirizzo affidabile e' quello aggiunto dal nostro proxy piu' esterno:
        # le voci alla sua sinistra le ha scritte il client.
        chain = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",")]
        if len(chain) >= hops and chain[-hops]:
            return chain[-hops]
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request, redis: Cache) -> None:
    limit = request.app.state.settings.api_rate_per_minute
    if not await allow_request(redis, client_ip(request), limit):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded",
                            headers={"Retry-After": "60"})


router = APIRouter(prefix="/api/v1", dependencies=[Depends(rate_limit)])


def _validate_filters(values: list[str]) -> None:
    if len(values) > MAX_FILTER_VALUES:
        raise HTTPException(422, "too many filter values")


async def _feed_response(
    request: Request, response: Response, *,
    pool: asyncpg.Pool, redis: Redis, feed_filter: repo.FeedFilter, limit: int,
    cursor: str | None, cache_control: str,
) -> Response:
    settings = request.app.state.settings
    if cursor:
        try:
            repo.decode_cursor(cursor)
        except repo.InvalidCursor:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from None

    async def compute() -> str:
        return json.dumps(await repo.fetch_feed(pool, feed_filter, limit, cursor),
                          separators=(",", ":"), ensure_ascii=False)

    params = {"c": sorted(feed_filter.categories), "t": sorted(feed_filter.tickers),
              "any": feed_filter.match_any, "q": feed_filter.search, "l": limit, "cur": cursor}
    body, cache_state = await cached_json(
        redis, params, compute,
        ttl_s=settings.feed_cache_ttl_s, stale_ttl_s=settings.feed_cache_stale_ttl_s)

    etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": cache_control, "X-Cache": cache_state}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


@router.get("/feed", response_model=FeedResponse, summary="Feed paginato con cursore")
async def get_feed(
    request: Request, response: Response, pool: Pool, redis: Cache,
    scope: Annotated[Literal["all", "top"], Query(description="top = tab Top News")] = "all",
    category: Annotated[list[str], Query()] = [],
    ticker: Annotated[list[str], Query()] = [],
    match: Annotated[Literal["all", "any"], Query(description="any = ticker OPPURE categoria")] = "all",
    q: Annotated[str | None, Query(min_length=2, max_length=80, description="Titolo, sommario o ticker")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> Response:
    _validate_filters(category)
    _validate_filters(ticker)
    categories = tuple(category)
    if scope == "top" and not categories:
        categories = await repo.top_news_categories(pool)
    feed_filter = repo.FeedFilter(categories=categories,
                                  tickers=tuple(value.upper() for value in ticker),
                                  match_any=match == "any", search=q.strip() if q else None)
    return await _feed_response(request, response, pool=pool, redis=redis, feed_filter=feed_filter,
                                limit=limit, cursor=cursor, cache_control="public, max-age=15")


@router.get("/feed/watchlist", response_model=FeedResponse, summary="Feed personalizzato")
async def get_watchlist_feed(
    request: Request, response: Response, pool: Pool, redis: Cache, user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> Response:
    watchlist = await repo.get_watchlist(pool, user)
    if not watchlist["tickers"] and not watchlist["categories"]:
        # Una watchlist vuota non significa "tutto": il client mostra l'onboarding.
        return JSONResponse({"data": [], "page_info": {
            "next_cursor": None, "has_more": False, "limit": limit}})
    # La cache e' per contenuto del filtro, non per utente: chi segue le stesse
    # cose condivide la stessa voce.
    feed_filter = repo.FeedFilter(categories=tuple(watchlist["categories"]),
                                  tickers=tuple(watchlist["tickers"]), match_any=True)
    return await _feed_response(request, response, pool=pool, redis=redis, feed_filter=feed_filter,
                                limit=limit, cursor=cursor, cache_control="private, max-age=15")


@router.get("/markets", summary="Barra mercati e stato di apertura")
async def get_markets(pool: Pool, response: Response) -> dict:
    response.headers["Cache-Control"] = "public, max-age=60"
    return {"market_open": is_market_open(datetime.now(timezone.utc)),
            "quotes": await fetch_markets(pool)}


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(pool: Pool) -> list[dict[str, str]]:
    rows = await pool.fetch("SELECT slug, label FROM categories ORDER BY sort_order")
    return [dict(row) for row in rows]


@router.get("/calendar", response_model=CalendarResponse, summary="Eventi economici del giorno")
async def get_calendar(
    pool: Pool,
    day: Annotated[date | None, Query(alias="date")] = None,
    tz: Annotated[str, Query(description="Fuso IANA del dispositivo")] = "UTC",
    country: Annotated[list[str], Query()] = [],
    impact: Annotated[list[Literal["low", "medium", "high", "holiday"]], Query()] = [],
) -> dict:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown timezone") from None
    _validate_filters(country)
    # "Oggi" dipende dal fuso dell'utente: i confini del giorno si calcolano li'.
    day = day or datetime.now(zone).date()
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    next_day = day + timedelta(days=1)
    end = datetime(next_day.year, next_day.month, next_day.day, tzinfo=zone)
    events = await repo.fetch_events(pool, start, end, [c.upper() for c in country], list(impact))
    return {"date": day.isoformat(), "timezone": tz, "data": events}


@router.get("/me/watchlist", response_model=Watchlist)
async def read_watchlist(pool: Pool, user: CurrentUser) -> dict[str, list[str]]:
    return await repo.get_watchlist(pool, user)


@router.put("/me/watchlist", response_model=Watchlist)
async def write_watchlist(body: Watchlist, pool: Pool, user: CurrentUser) -> dict[str, list[str]]:
    try:
        await repo.replace_watchlist(pool, user, body.tickers, list(dict.fromkeys(body.categories)))
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(422, "unknown category") from None
    except asyncpg.CheckViolationError:
        raise HTTPException(422, "invalid ticker") from None
    return await repo.get_watchlist(pool, user)


@router.get("/me/bookmarks", response_model=list[ArticleOut])
async def list_bookmarks(
    pool: Pool, user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> list[dict]:
    return await repo.fetch_bookmarks(pool, user, limit)


@router.put("/me/bookmarks/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_bookmark(article_id: UUID, pool: Pool, user: CurrentUser) -> None:
    try:
        await pool.execute(
            "INSERT INTO user_bookmarks (user_id, article_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            user, article_id)
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found") from None


@router.delete("/me/bookmarks/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bookmark(article_id: UUID, pool: Pool, user: CurrentUser) -> None:
    await pool.execute("DELETE FROM user_bookmarks WHERE user_id = $1 AND article_id = $2",
                       user, article_id)


app = FastAPI(title="ClearMarket API", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/healthz", include_in_schema=False)
async def healthz(request: Request) -> JSONResponse:
    """Readiness: Redis e' opzionale, Postgres no."""
    checks = {"postgres": True, "redis": True}
    try:
        await request.app.state.pool.fetchval("SELECT 1")
    except (asyncpg.PostgresError, OSError):
        checks["postgres"] = False
    try:
        await request.app.state.redis.ping()
    except (RedisError, OSError):
        checks["redis"] = False
    return JSONResponse(checks, status_code=200 if checks["postgres"] else 503)
