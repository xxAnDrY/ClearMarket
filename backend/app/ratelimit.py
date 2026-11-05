"""Rate limiting distribuito su Redis: in uscita verso i provider, in ingresso sull'API."""
import asyncio
import random
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

# Token bucket atomico: piu' repliche del worker condividono lo stesso budget.
# Restituisce 0 se il token e' stato preso, altrimenti i ms da attendere.
_TOKEN_BUCKET_LUA = """
local key, rate_per_ms, capacity, now_ms = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
local state = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(state[1]) or capacity
local ts = tonumber(state[2]) or now_ms
tokens = math.min(capacity, tokens + math.max(0, now_ms - ts) * rate_per_ms)
local wait_ms = 0
if tokens >= 1 then
  tokens = tokens - 1
else
  wait_ms = math.ceil((1 - tokens) / rate_per_ms)
end
redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(now_ms))
redis.call('PEXPIRE', key, math.ceil(capacity / rate_per_ms) + 1000)
return wait_ms
"""


class TokenBucket:
    def __init__(self, redis: Redis, name: str, rate_per_minute: int) -> None:
        self._redis = redis
        self._key = f"ratelimit:bucket:{name}"
        self._rate_per_ms = rate_per_minute / 60_000
        # Burst contenuto: il provider conta anche i picchi al secondo.
        self._capacity = max(1, rate_per_minute // 6)
        self._script = redis.register_script(_TOKEN_BUCKET_LUA)

    async def acquire(self) -> None:
        """Attende finche' non ottiene un token."""
        while True:
            wait_ms = await self._script(
                keys=[self._key],
                args=[self._rate_per_ms, self._capacity, int(time.time() * 1000)],
            )
            if not wait_ms:
                return
            # Il jitter evita che le repliche si risveglino tutte insieme.
            await asyncio.sleep(wait_ms / 1000 * random.uniform(1.0, 1.2))

    async def penalize(self, seconds: float) -> None:
        """Dopo un 429 azzera il budget, cosi' tutte le repliche si fermano."""
        now_ms = int(time.time() * 1000)
        debt = -seconds * 1000 * self._rate_per_ms
        await self._redis.hset(self._key, mapping={"tokens": str(debt), "ts": str(now_ms)})


async def allow_request(redis: Redis, client_id: str, limit_per_minute: int) -> bool:
    """Finestra fissa per client. Fail-open: Redis giu' non deve spegnere l'API."""
    window = int(time.time() // 60)
    key = f"ratelimit:api:{client_id}:{window}"
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 120)
            count, _ = await pipe.execute()
    except (RedisError, OSError):
        return True
    return count <= limit_per_minute
