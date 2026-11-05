-- ClearMarket: schema iniziale (PostgreSQL 14+ / Supabase).
-- Idempotente solo sulle estensioni: le migrazioni vanno applicate una volta, in ordine.

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- similarity() per la near-deduplicazione dei titoli

-- ---------------------------------------------------------------------------
-- categories: tassonomia chiusa, la slug e' la chiave pubblica usata dalle API.
-- ---------------------------------------------------------------------------
CREATE TABLE categories (
    slug        TEXT PRIMARY KEY CHECK (slug ~ '^[a-z][a-z0-9_]*$'),
    label       TEXT NOT NULL,
    in_top_news BOOLEAN NOT NULL DEFAULT TRUE,  -- appartiene al tab "Top News"
    sort_order  SMALLINT NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- sources: registro delle fonti E stato dello scheduler di polling.
-- Aggiungere una fonte RSS e' una INSERT, non un deploy.
-- ---------------------------------------------------------------------------
CREATE TYPE source_kind AS ENUM ('rss', 'finnhub_news', 'finnhub_company', 'ff_calendar');

CREATE TABLE sources (
    id                   SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug                 TEXT NOT NULL UNIQUE,
    name                 TEXT NOT NULL,              -- nome mostrato nella card
    kind                 source_kind NOT NULL,
    url                  TEXT NOT NULL,
    default_category     TEXT NOT NULL REFERENCES categories (slug),
    enabled              BOOLEAN NOT NULL DEFAULT TRUE,
    poll_interval_s      INTEGER NOT NULL DEFAULT 300 CHECK (poll_interval_s >= 30),

    -- Stato scheduler
    next_poll_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_success_at      TIMESTAMPTZ,
    last_error           TEXT,

    -- Conditional GET: una risposta 304 non consuma parsing ne' scritture.
    http_etag            TEXT,
    http_last_modified   TEXT,
    -- Cursore del provider (es. minId di Finnhub) per chiedere solo il nuovo.
    provider_cursor      TEXT
);

CREATE INDEX sources_due_idx ON sources (next_poll_at) WHERE enabled;

-- ---------------------------------------------------------------------------
-- articles
-- ---------------------------------------------------------------------------
CREATE TYPE sentiment_label AS ENUM ('positive', 'neutral', 'negative');

CREATE TABLE articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       SMALLINT NOT NULL REFERENCES sources (id),
    category        TEXT NOT NULL REFERENCES categories (slug),
    title           TEXT NOT NULL CHECK (length(title) > 0),
    summary         TEXT NOT NULL DEFAULT '',
    url             TEXT NOT NULL CHECK (url ~* '^https?://'),
    published_at    TIMESTAMPTZ NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    related_tickers TEXT[] NOT NULL DEFAULT '{}',
    sentiment       sentiment_label NOT NULL DEFAULT 'neutral',
    sentiment_score REAL NOT NULL DEFAULT 0 CHECK (sentiment_score BETWEEN -1 AND 1),

    -- Deduplicazione a tre livelli, vedi app/ingestion/dedupe.py
    url_hash        BYTEA NOT NULL UNIQUE,    -- L1: stessa URL canonica => scartato
    title_hash      BYTEA NOT NULL,           -- L2: stesso titolo normalizzato
    -- L2/L3: la riga resta (nessuna perdita di dati su un falso positivo) ma
    -- punta all'articolo canonico e il feed non la mostra.
    duplicate_of    UUID REFERENCES articles (id) ON DELETE SET NULL
);

-- Keyset pagination del feed: l'ordine dell'indice coincide con ORDER BY.
CREATE INDEX articles_feed_idx
    ON articles (published_at DESC, id DESC) WHERE duplicate_of IS NULL;
CREATE INDEX articles_category_feed_idx
    ON articles (category, published_at DESC, id DESC) WHERE duplicate_of IS NULL;
CREATE INDEX articles_tickers_idx
    ON articles USING GIN (related_tickers) WHERE duplicate_of IS NULL;

-- Supporto alla deduplicazione.
-- L3 non ha un indice trigrammi: la finestra su published_at usa gia' articles_feed_idx
-- e lascia pochi candidati, mentre un GIN rallenterebbe ogni INSERT.
CREATE INDEX articles_title_hash_idx ON articles (title_hash, published_at DESC);

-- ---------------------------------------------------------------------------
-- user_watchlist: una riga per ticker O categoria seguiti.
-- user_id e' il claim "sub" del JWT (Supabase Auth): nessuna FK verso auth.users
-- cosi' lo schema gira anche su un Postgres locale senza Supabase.
-- ---------------------------------------------------------------------------
CREATE TABLE user_watchlist (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    UUID NOT NULL,
    ticker     TEXT CHECK (ticker ~ '^[A-Z0-9][A-Z0-9.\-]{0,14}$'),
    category   TEXT REFERENCES categories (slug) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(ticker, category) = 1)
);

CREATE UNIQUE INDEX user_watchlist_ticker_uq
    ON user_watchlist (user_id, ticker) WHERE ticker IS NOT NULL;
CREATE UNIQUE INDEX user_watchlist_category_uq
    ON user_watchlist (user_id, category) WHERE category IS NOT NULL;
-- Il worker chiede l'unione dei ticker seguiti per decidere cosa interrogare.
CREATE INDEX user_watchlist_ticker_idx ON user_watchlist (ticker) WHERE ticker IS NOT NULL;

-- ---------------------------------------------------------------------------
-- user_bookmarks
-- ---------------------------------------------------------------------------
CREATE TABLE user_bookmarks (
    user_id    UUID NOT NULL,
    article_id UUID NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, article_id)
);

-- ---------------------------------------------------------------------------
-- economic_events: tab "Calendario Economico".
-- actual/forecast/previous restano testo: il dato grezzo e' "3.2%", "245K", "-0.1B".
-- ---------------------------------------------------------------------------
CREATE TYPE event_impact AS ENUM ('low', 'medium', 'high', 'holiday');

CREATE TABLE economic_events (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id  SMALLINT NOT NULL REFERENCES sources (id),
    title      TEXT NOT NULL,
    country    TEXT NOT NULL,                  -- valuta dell'evento: USD, EUR, GBP...
    starts_at  TIMESTAMPTZ NOT NULL,
    impact     event_impact NOT NULL,
    forecast   TEXT,
    previous   TEXT,
    actual     TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (title, country, starts_at)         -- rende l'upsert del worker idempotente
);

CREATE INDEX economic_events_day_idx ON economic_events (starts_at);
