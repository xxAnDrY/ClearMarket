-- Barra mercati: ultimo valore noto di ogni strumento, aggiornato dal worker.
CREATE TABLE market_quotes (
    symbol     TEXT PRIMARY KEY,
    label      TEXT NOT NULL,
    value      DOUBLE PRECISION NOT NULL,
    change_pct DOUBLE PRECISION,          -- NULL: variazione non disponibile (spread)
    unit       TEXT NOT NULL DEFAULT '',
    decimals   SMALLINT NOT NULL DEFAULT 0,
    sort_order SMALLINT NOT NULL DEFAULT 0,
    as_of      TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
