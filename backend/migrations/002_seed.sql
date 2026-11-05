-- Tassonomia e fonti iniziali. URL RSS verificati il 2026-11-05 (HTTP 200).
INSERT INTO categories (slug, label, in_top_news, sort_order) VALUES
    ('macro',           'Macroeconomia',       TRUE,  10),
    ('monetary_policy', 'Politica monetaria',  TRUE,  20),
    ('stocks_eu',       'Azioni UE',           TRUE,  30),
    ('stocks_us',       'Azioni USA',          TRUE,  40),
    ('etf',             'ETF',                 FALSE, 50),
    ('crypto',          'Crypto',              FALSE, 60);

INSERT INTO sources (slug, name, kind, url, default_category, poll_interval_s) VALUES
    -- I due feed RSS di base: fonti primarie, aggiornate solo ad ogni comunicato.
    ('ecb-press',  'BCE',          'rss', 'https://www.ecb.europa.eu/rss/press.html',           'monetary_policy', 300),
    ('fed-press',  'Federal Reserve', 'rss', 'https://www.federalreserve.gov/feeds/press_all.xml', 'monetary_policy', 300),
    -- Copertura mercati e crypto.
    -- Feed tematici: i "top stories" generalisti mescolano sport e finanza personale.
    ('cnbc-investing', 'CNBC', 'rss', 'https://www.cnbc.com/id/15839069/device/rss/rss.html', 'stocks_us', 180),
    ('cnbc-economy',   'CNBC', 'rss', 'https://www.cnbc.com/id/20910258/device/rss/rss.html', 'macro',     180),
    ('coindesk',   'CoinDesk',     'rss', 'https://www.coindesk.com/arc/outboundfeeds/rss',              'crypto',    300),
    -- API. Il token sta in FINNHUB_API_KEY, mai nell'URL salvato a DB.
    ('finnhub-general', 'Finnhub', 'finnhub_news',    'https://finnhub.io/api/v1/news?category=general', 'macro',     120),
    ('finnhub-crypto',  'Finnhub', 'finnhub_news',    'https://finnhub.io/api/v1/news?category=crypto',  'crypto',    300),
    -- Interroga a rotazione i ticker delle watchlist: un'unica riga scheduler.
    ('finnhub-company', 'Finnhub', 'finnhub_company', 'https://finnhub.io/api/v1/company-news',          'stocks_us', 60),
    -- Calendario: JSON pubblico settimanale, non ufficiale. Vedi docs/ARCHITECTURE.md §7.
    ('ff-calendar', 'Forex Factory', 'ff_calendar', 'https://nfs.faireconomy.media/ff_calendar_thisweek.json', 'macro', 3600);
