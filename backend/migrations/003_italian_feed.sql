-- Feed in italiano: fonti italiane, traduzione delle estere, polling per fasce orarie.

-- Copertura richiesta: politica economica, microeconomia, bond, materie prime.
INSERT INTO categories (slug, label, in_top_news, sort_order) VALUES
    ('fiscal_policy',  'Politica economica', TRUE, 25),
    ('microeconomics', 'Microeconomia',      TRUE, 26),
    ('bonds',          'Obbligazioni',       TRUE, 45),
    ('commodities',    'Materie prime',      TRUE, 46);

-- ---------------------------------------------------------------------------
-- sources: lingua e secondo intervallo di polling.
-- poll_interval_s vale a mercato aperto, closed_poll_interval_s a mercato chiuso.
-- ---------------------------------------------------------------------------
ALTER TABLE sources
    ADD COLUMN language TEXT NOT NULL DEFAULT 'en' CHECK (language ~ '^[a-z]{2}$'),
    ADD COLUMN closed_poll_interval_s INTEGER NOT NULL DEFAULT 3600
        CHECK (closed_poll_interval_s >= 60);

UPDATE sources SET poll_interval_s = 600, closed_poll_interval_s = 3600
    WHERE slug IN ('ecb-press', 'fed-press', 'coindesk', 'finnhub-crypto', 'finnhub-company');
UPDATE sources SET poll_interval_s = 300, closed_poll_interval_s = 1800
    WHERE slug IN ('cnbc-investing', 'cnbc-economy', 'finnhub-general');
-- Il JSON del calendario e' pubblico e si aggiorna poche volte al giorno.
UPDATE sources SET poll_interval_s = 3600, closed_poll_interval_s = 3600
    WHERE slug = 'ff-calendar';

-- URL verificati il 2026-11-05. Milano Finanza e Teleborsa non espongono un RSS
-- pubblico e Reuters ha chiuso i suoi: non vengono fatti scraping dei siti.
INSERT INTO sources (slug, name, kind, url, default_category, language,
                     poll_interval_s, closed_poll_interval_s) VALUES
    ('sole24-economia', 'Il Sole 24 Ore', 'rss', 'https://www.ilsole24ore.com/rss/economia.xml',
     'macro',     'it', 300, 1800),
    ('sole24-finanza',  'Il Sole 24 Ore', 'rss', 'https://www.ilsole24ore.com/rss/finanza.xml',
     'stocks_eu', 'it', 300, 1800),
    ('ansa-economia',   'ANSA Economia',  'rss', 'https://www.ansa.it/sito/notizie/economia/economia_rss.xml',
     'macro',     'it', 300, 1800),
    ('finanzaonline',   'FinanzaOnline',  'rss', 'https://www.finanzaonline.com/feed',
     'stocks_eu', 'it', 300, 1800),
    ('bloomberg-markets',   'Bloomberg', 'rss', 'https://feeds.bloomberg.com/markets/news.rss',
     'stocks_us', 'en', 600, 3600),
    ('bloomberg-economics', 'Bloomberg', 'rss', 'https://feeds.bloomberg.com/economics/news.rss',
     'macro',     'en', 600, 3600);

-- ---------------------------------------------------------------------------
-- articles: link alla fonte e stato della traduzione.
-- ---------------------------------------------------------------------------
ALTER TABLE articles RENAME COLUMN url TO source_url;

ALTER TABLE articles
    ADD COLUMN language TEXT NOT NULL DEFAULT 'it',
    ADD COLUMN title_original TEXT,
    ADD COLUMN summary_original TEXT NOT NULL DEFAULT '',
    -- pending e failed restano fuori dal feed: mai testo non italiano a schermo.
    ADD COLUMN translation_status TEXT NOT NULL DEFAULT 'not_needed'
        CHECK (translation_status IN ('not_needed', 'pending', 'done', 'failed')),
    ADD COLUMN translation_attempts SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN translated_by TEXT,
    -- Lease: una replica che muore rilascia il lavoro alla scadenza.
    ADD COLUMN translate_after TIMESTAMPTZ NOT NULL DEFAULT now();

-- Gli articoli gia' raccolti vengono dalle fonti estere: entrano nella coda.
UPDATE articles a
SET language = s.language,
    title_original = a.title,
    summary_original = a.summary,
    translation_status = CASE WHEN s.language = 'it' THEN 'not_needed' ELSE 'pending' END
FROM sources s
WHERE s.id = a.source_id;

ALTER TABLE articles
    ALTER COLUMN title_original SET NOT NULL,
    ADD COLUMN visible BOOLEAN GENERATED ALWAYS AS (
        duplicate_of IS NULL AND translation_status IN ('not_needed', 'done')
    ) STORED;

DROP INDEX articles_feed_idx;
DROP INDEX articles_category_feed_idx;
DROP INDEX articles_tickers_idx;
CREATE INDEX articles_feed_idx ON articles (published_at DESC, id DESC) WHERE visible;
CREATE INDEX articles_category_feed_idx
    ON articles (category, published_at DESC, id DESC) WHERE visible;
CREATE INDEX articles_tickers_idx ON articles USING GIN (related_tickers) WHERE visible;
CREATE INDEX articles_translation_queue_idx
    ON articles (published_at DESC) WHERE translation_status = 'pending';
-- La finestra della deduplicazione L3 non puo' piu' appoggiarsi agli indici del feed,
-- perche' gli articoli in attesa di traduzione non ne fanno parte.
CREATE INDEX articles_published_idx ON articles (published_at DESC);
