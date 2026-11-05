"""Cache del feed su Redis.

Invalidazione per versione: la chiave contiene `feed:version`; il worker la incrementa
quando arrivano articoli nuovi e le vecchie chiavi muoiono per TTL, senza SCAN/DEL.

Ogni valore vive piu' a lungo della sua freschezza (`stale_ttl`). Questo copre due casi:
 - stampede: alla scadenza un solo processo ricalcola (lock SET NX), gli altri servono
   la copia stale invece di colpire tutti il database;
 - errori: se il DB fallisce si serve la copia stale.

Qualsiasi errore Redis degrada a "cache miss": l'API continua a rispondere da Postgres.
"""
import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

VERSION_KEY = "feed:version"
_LOCK_TTL_S = 5
_LOCK_POLL_S = 0.05
_LOCK_MAX_WAIT_S = 1.0


async def bump_feed_version(redis: Redis) -> None:
    await redis.incr(VERSION_KEY)


def cache_key(version: str, params: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:32]
    return f"feed:v{version}:{digest}"


async def cached_json(
    redis: Redis,
    params: dict[str, Any],
    compute: Callable[[], Awaitable[str]],
    *,
    ttl_s: int,
    stale_ttl_s: int,
) -> tuple[str, str]:
    """Restituisce (body JSON, stato) con stato in hit | stale | miss | bypass."""
    try:
        version = await redis.get(VERSION_KEY) or "0"
        key = cache_key(str(version), params)
        cached = await redis.get(key)
    except (RedisError, OSError) as exc:
        log.warning("redis unavailable, bypassing cache: %r", exc)
        return await compute(), "bypass"

    fresh_until = 0.0
    body = None
    if cached:
        fresh_until, body = cached.split("|", 1)
        fresh_until = float(fresh_until)
        if time.time() < fresh_until:
            return body, "hit"

    try:
        got_lock = await redis.set(f"{key}:lock", "1", nx=True, ex=_LOCK_TTL_S)
    except (RedisError, OSError):
        got_lock = True  # senza Redis non c'e' coordinamento: calcola e basta

    if not got_lock:
        if body is not None:
            return body, "stale"
        # Primo accesso a questa chiave: attendi brevemente chi sta gia' calcolando.
        deadline = time.monotonic() + _LOCK_MAX_WAIT_S
        while time.monotonic() < deadline:
            await asyncio.sleep(_LOCK_POLL_S)
            try:
                cached = await redis.get(key)
            except (RedisError, OSError):
                break
            if cached:
                return cached.split("|", 1)[1], "hit"

    try:
        computed = await compute()
    except Exception:
        if body is not None:
            log.exception("feed query failed, serving stale copy")
            return body, "stale"
        raise

    try:
        payload = f"{time.time() + ttl_s}|{computed}"
        await redis.set(key, payload, ex=stale_ttl_s)
        if got_lock:
            await redis.delete(f"{key}:lock")
    except (RedisError, OSError) as exc:
        log.warning("cache write failed: %r", exc)
    return computed, "miss"
