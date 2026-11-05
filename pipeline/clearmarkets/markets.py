"""Valori della barra mercati.

Solo dati reali: se una fonte non risponde resta l'ultimo valore noto, con la sua data, e
dopo qualche giorno lo strumento sparisce. Nessun valore viene stimato.

Indici, cambio e Bitcoin arrivano dall'endpoint chart di Yahoo Finance, non ufficiale e con
quotazioni ritardate. Per lo spread BTP/Bund non esiste una fonte gratuita affidabile: il dato
viene letto dalle notizie italiane gia' raccolte ("Lo spread ... a 109 punti").
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

log = logging.getLogger("clearmarkets.markets")

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SPREAD_SYMBOL = "BTP-BUND"
# "a NNN punti": esclude le variazioni come "scende di 10 punti".
_SPREAD = re.compile(r"\bspread\b[^.]*?\ba\s+(\d{2,3})(?:,\d+)?\s+punti", re.IGNORECASE)

INSTRUMENTS = (
    {"symbol": "FTSEMIB.MI", "label": "FTSE MIB", "decimals": 0, "unit": "", "order": 10},
    {"symbol": "^GSPC", "label": "S&P 500", "decimals": 0, "unit": "", "order": 20},
    {"symbol": "EURUSD=X", "label": "EUR/USD", "decimals": 4, "unit": "", "order": 30},
    {"symbol": "BTC-USD", "label": "Bitcoin", "decimals": 0, "unit": "$", "order": 50},
)


def parse_chart(payload: dict[str, Any]) -> tuple[float, float, datetime]:
    """Prezzo, variazione percentuale e orario. KeyError/TypeError se il formato cambia."""
    meta = payload["chart"]["result"][0]["meta"]
    price = float(meta["regularMarketPrice"])
    previous = float(meta.get("previousClose") or meta["chartPreviousClose"])
    as_of = datetime.fromtimestamp(meta["regularMarketTime"], timezone.utc)
    return price, round((price - previous) / previous * 100, 2), as_of


def parse_spread(text: str) -> int | None:
    match = _SPREAD.search(text)
    return int(match.group(1)) if match else None


async def refresh_quotes(client: httpx.AsyncClient, quotes: dict[str, dict[str, Any]]) -> int:
    updated = 0
    for item in INSTRUMENTS:
        try:
            response = await client.get(YAHOO_URL.format(symbol=quote(item["symbol"], safe="")),
                                        params={"range": "1d", "interval": "1d"})
            response.raise_for_status()
            price, change, as_of = parse_chart(response.json())
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
            log.warning("quote %s unavailable: %r", item["symbol"], exc)
            continue
        quotes[item["symbol"]] = {**item, "value": price, "change_pct": change, "as_of": as_of.isoformat()}
        updated += 1
    return updated


def refresh_spread(articles: list[dict[str, Any]], quotes: dict[str, dict[str, Any]]) -> bool:
    italian = [article for article in articles if article["language"] == "it"]
    for article in sorted(italian, key=lambda item: item["published_at"], reverse=True):
        value = parse_spread(article["title"]) or parse_spread(article["summary"])
        if value is not None:
            quotes[SPREAD_SYMBOL] = {
                "symbol": SPREAD_SYMBOL, "label": "Spread BTP/Bund", "decimals": 0, "unit": "pb",
                "order": 40, "value": float(value), "change_pct": None, "as_of": article["published_at"],
            }
            return True
    return False
