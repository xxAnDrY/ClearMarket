"""Configurazione da variabili d'ambiente (o `.env`), validata all'avvio."""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # Con PgBouncer in transaction mode (pooler Supabase, porta 6543) i prepared
    # statement lato server non sono utilizzabili: va impostato a 0.
    db_statement_cache_size: int = 0
    db_pool_max: int = 10

    # Auth: JWKS (consigliato, chiavi asimmetriche Supabase) o segreto HS256 (sviluppo).
    jwt_jwks_url: str | None = None
    jwt_secret: str | None = None
    jwt_audience: str = "authenticated"

    finnhub_api_key: str | None = None
    # Il piano gratuito dichiara 60 chiamate/min: restiamo sotto per assorbire
    # la deriva di clock e le richieste ripetute.
    finnhub_rate_per_minute: int = 50
    finnhub_company_batch: int = 10  # ticker interrogati per ogni ciclo

    # Traduzione: backend provati in ordine. deepl viene saltato senza chiave.
    translation_backends: str = "deepl,mymemory"
    deepl_api_key: str | None = None
    deepl_api_url: str = "https://api-free.deepl.com/v2/translate"
    translate_batch: int = 5        # articoli per giro della coda
    translate_tick_s: float = 10.0

    # Cache del feed
    feed_cache_ttl_s: int = 30
    feed_cache_stale_ttl_s: int = 300  # finestra stale-if-error / anti-stampede
    # Limite in ingresso per client sull'API pubblica.
    api_rate_per_minute: int = 120
    # Numero di reverse proxy davanti all'API: 0 = ignora X-Forwarded-For, che
    # altrimenti un client potrebbe falsificare per eludere il rate limit.
    trusted_proxy_hops: int = 0

    # Worker
    worker_tick_s: float = 5.0
    worker_concurrency: int = 4
    worker_lease_s: int = 120
    http_timeout_s: float = 15.0
    http_user_agent: str = "ClearMarketBot/0.1"
    near_dup_threshold: float = 0.72
    near_dup_window_hours: int = 12

    @model_validator(mode="after")
    def _normalize_dsn(self) -> "Settings":
        # asyncpg vuole lo schema nudo, non la forma SQLAlchemy.
        self.database_url = self.database_url.replace("postgresql+asyncpg://", "postgresql://")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
