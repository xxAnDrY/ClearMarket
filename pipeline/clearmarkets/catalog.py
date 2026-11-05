"""Fonti raccolte a ogni giro. URL RSS verificati il 2026-11-05.

Milano Finanza e Teleborsa non espongono un RSS pubblico e Reuters ha chiuso i suoi: non
vengono fatti scraping dei siti. Le notizie Reuters possono arrivare tramite Finnhub.
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Source:
    slug: str
    name: str
    kind: str              # rss | finnhub
    url: str
    default_category: str
    language: str = "en"


SOURCES = (
    Source("sole24-economia", "Il Sole 24 Ore", "rss", "https://www.ilsole24ore.com/rss/economia.xml", "macro", "it"),
    Source("sole24-finanza", "Il Sole 24 Ore", "rss", "https://www.ilsole24ore.com/rss/finanza.xml", "stocks_eu", "it"),
    Source("ansa-economia", "ANSA Economia", "rss", "https://www.ansa.it/sito/notizie/economia/economia_rss.xml", "macro", "it"),
    Source("finanzaonline", "FinanzaOnline", "rss", "https://www.finanzaonline.com/feed", "stocks_eu", "it"),
    Source("ecb-press", "BCE", "rss", "https://www.ecb.europa.eu/rss/press.html", "monetary_policy"),
    Source("fed-press", "Federal Reserve", "rss", "https://www.federalreserve.gov/feeds/press_all.xml", "monetary_policy"),
    Source("bloomberg-markets", "Bloomberg", "rss", "https://feeds.bloomberg.com/markets/news.rss", "stocks_us"),
    Source("bloomberg-economics", "Bloomberg", "rss", "https://feeds.bloomberg.com/economics/news.rss", "macro"),
    Source("cnbc-investing", "CNBC", "rss", "https://www.cnbc.com/id/15839069/device/rss/rss.html", "stocks_us"),
    Source("cnbc-economy", "CNBC", "rss", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "macro"),
    Source("coindesk", "CoinDesk", "rss", "https://www.coindesk.com/arc/outboundfeeds/rss", "crypto"),
    # Saltate senza FINNHUB_API_KEY.
    Source("finnhub-general", "Finnhub", "finnhub", "https://finnhub.io/api/v1/news?category=general", "macro"),
    Source("finnhub-crypto", "Finnhub", "finnhub", "https://finnhub.io/api/v1/news?category=crypto", "crypto"),
)
