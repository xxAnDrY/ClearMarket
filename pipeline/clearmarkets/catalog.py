"""Fonti raccolte a ogni giro. URL verificati il 2026-11-05.

Ogni notizia resta nella sua lingua originale. Milano Finanza, Teleborsa e Reuters non espongono
un RSS pubblico funzionante: non vengono fatti scraping dei siti. Le notizie Reuters possono
arrivare tramite Finnhub.
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


def _it(slug: str, name: str, url: str, category: str) -> Source:
    return Source(slug, name, "rss", url, category, "it")


def _en(slug: str, name: str, url: str, category: str) -> Source:
    return Source(slug, name, "rss", url, category)


CNBC = "https://www.cnbc.com/id/{}/device/rss/rss.html"
BLOOMBERG = "https://feeds.bloomberg.com/{}/news.rss"
DOW_JONES = "https://feeds.content.dowjones.io/public/rss/{}"
INVESTING = "https://www.investing.com/rss/{}.rss"
SOLE = "https://www.ilsole24ore.com/rss/{}.xml"

SOURCES = (
    # Italiano
    _it("sole24-economia", "Il Sole 24 Ore", SOLE.format("economia"), "macro"),
    _it("sole24-finanza", "Il Sole 24 Ore", SOLE.format("finanza"), "stocks_eu"),
    _it("sole24-mondo", "Il Sole 24 Ore", SOLE.format("mondo"), "macro"),
    _it("sole24-norme", "Il Sole 24 Ore", SOLE.format("norme-e-tributi"), "fiscal_policy"),
    _it("ansa-economia", "ANSA Economia", "https://www.ansa.it/sito/notizie/economia/economia_rss.xml", "macro"),
    _it("finanzaonline", "FinanzaOnline", "https://www.finanzaonline.com/feed", "stocks_eu"),
    _it("repubblica-economia", "la Repubblica", "https://www.repubblica.it/rss/economia/rss2.0.xml", "macro"),
    _it("wallstreetitalia", "Wall Street Italia", "https://www.wallstreetitalia.com/feed/", "stocks_eu"),
    _it("quifinanza", "QuiFinanza", "https://quifinanza.it/feed/", "microeconomics"),
    _it("money-it", "Money.it", "https://www.money.it/spip.php?page=backend", "macro"),
    _it("investing-it", "Investing.com Italia", "https://it.investing.com/rss/news.rss", "stocks_eu"),
    # Banche centrali
    _en("ecb-press", "BCE", "https://www.ecb.europa.eu/rss/press.html", "monetary_policy"),
    _en("fed-press", "Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", "monetary_policy"),
    _en("boe-news", "Bank of England", "https://www.bankofengland.co.uk/rss/news", "monetary_policy"),
    # Mercati ed economia
    _en("bloomberg-markets", "Bloomberg", BLOOMBERG.format("markets"), "stocks_us"),
    _en("bloomberg-economics", "Bloomberg", BLOOMBERG.format("economics"), "macro"),
    _en("bloomberg-politics", "Bloomberg", BLOOMBERG.format("politics"), "fiscal_policy"),
    _en("bloomberg-technology", "Bloomberg", BLOOMBERG.format("technology"), "stocks_us"),
    _en("cnbc-investing", "CNBC", CNBC.format(15839069), "stocks_us"),
    _en("cnbc-economy", "CNBC", CNBC.format(20910258), "macro"),
    _en("cnbc-finance", "CNBC", CNBC.format(10000664), "stocks_us"),
    _en("cnbc-earnings", "CNBC", CNBC.format(15839135), "stocks_us"),
    _en("cnbc-world", "CNBC", CNBC.format(100727362), "macro"),
    _en("cnbc-technology", "CNBC", CNBC.format(19854910), "stocks_us"),
    _en("cnbc-politics", "CNBC", CNBC.format(10001147), "fiscal_policy"),
    _en("marketwatch-top", "MarketWatch", DOW_JONES.format("mw_topstories"), "stocks_us"),
    _en("marketwatch-bulletins", "MarketWatch", DOW_JONES.format("mw_bulletins"), "stocks_us"),
    _en("investing-news", "Investing.com", INVESTING.format("news"), "stocks_us"),
    _en("investing-stocks", "Investing.com", INVESTING.format("news_25"), "stocks_us"),
    _en("investing-economy", "Investing.com", INVESTING.format("news_14"), "macro"),
    _en("seekingalpha", "Seeking Alpha", "https://seekingalpha.com/market_currents.xml", "stocks_us"),
    _en("ft-markets", "Financial Times", "https://www.ft.com/markets?format=rss", "stocks_us"),
    _en("economist-finance", "The Economist", "https://www.economist.com/finance-and-economics/rss.xml", "macro"),
    _en("nyt-business", "The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "stocks_us"),
    _en("nyt-economy", "The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml", "macro"),
    _en("bbc-business", "BBC", "https://feeds.bbci.co.uk/news/business/rss.xml", "macro"),
    _en("guardian-business", "The Guardian", "https://www.theguardian.com/uk/business/rss", "macro"),
    _en("guardian-economics", "The Guardian", "https://www.theguardian.com/business/economics/rss", "macro"),
    _en("thestreet", "TheStreet", "https://www.thestreet.com/.rss/full/", "stocks_us"),
    # ETF e crypto
    _en("etftrends", "ETF Trends", "https://www.etftrends.com/feed/", "etf"),
    _en("coindesk", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss", "crypto"),
    _en("cointelegraph", "Cointelegraph", "https://cointelegraph.com/rss", "crypto"),
    _en("decrypt", "Decrypt", "https://decrypt.co/feed", "crypto"),
    # Saltate senza FINNHUB_API_KEY.
    Source("finnhub-general", "Finnhub", "finnhub", "https://finnhub.io/api/v1/news?category=general", "macro"),
    Source("finnhub-crypto", "Finnhub", "finnhub", "https://finnhub.io/api/v1/news?category=crypto", "crypto"),
)
