"""Fixture su un vero PostgreSQL e Redis simulato (con Lua reale).

TEST_DATABASE_URL deve puntare a un database usa-e-getta: lo schema viene ricreato.
"""
import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import fakeredis
import pytest
import pytest_asyncio

os.environ["DATABASE_URL"] = "postgresql://unused"
os.environ["JWT_SECRET"] = "test-secret-with-at-least-32-bytes!!"
os.environ.pop("JWT_JWKS_URL", None)

MIGRATIONS = Path(__file__).parent.parent / "migrations"


@pytest_asyncio.fixture(scope="session")
async def pool() -> AsyncIterator[asyncpg.Pool]:
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.exit("Imposta TEST_DATABASE_URL (database usa-e-getta)", returncode=2)
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            await conn.execute(path.read_text(encoding="utf-8"))
    yield pool
    await pool.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(pool: asyncpg.Pool) -> None:
    await pool.execute(
        "TRUNCATE articles, user_watchlist, user_bookmarks, economic_events CASCADE")
    await pool.execute(
        """UPDATE sources SET next_poll_at = now(), consecutive_failures = 0, last_error = NULL,
           http_etag = NULL, http_last_modified = NULL, provider_cursor = NULL""")


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[fakeredis.FakeAsyncRedis]:
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()
