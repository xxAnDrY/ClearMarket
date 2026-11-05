"""Pool asyncpg condiviso da API e worker."""
import asyncpg

from app.config import Settings


async def create_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=settings.db_pool_max,
        statement_cache_size=settings.db_statement_cache_size,
        command_timeout=10,
    )
