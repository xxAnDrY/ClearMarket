"""Valori della barra mercati.

Solo dati reali: se una fonte non risponde resta l'ultimo valore noto, con la sua data, e
dopo qualche giorno lo strumento sparisce dalla barra. Nessun valore viene stimato.

Indici, cambio e Bitcoin arrivano dall'endpoint chart di Yahoo Finance, non ufficiale e con
quotazioni spesso ritardate. Per lo spread BTP/Bund non esiste una fonte gratuita affidabile:
il dato viene letto dalle notizie ANSA gia' raccolte ("Lo spread ... a 109 punti").
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import asyncpg
import httpx

log = logging.getLogger("clearmarket.markets")

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SPREAD_SYMBOL = "BTP-BUND"
# "a NNN punti": esclude le variazioni come "scende di 10 punti".
_SPREAD = re.compile(r"\bspread\b[^.]*?\ba\s+(\d{2,3})(?:,\d+)?\s+punti", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    label: str
    decimals: int
    unit: str
    sort_order: int


INSTRUMENTS = (
    Instrument("FTSEMIB.MI", "FTSE MIB", 0, "", 10),
    Instrument("^GSPC", "S&P 500", 0, "", 20),
    Instrument("EURUSD=X", "EUR/USD", 4, "", 30),
    Instrument("BTC-USD", "Bitcoin", 0, "$", 50),
)

_UPSERT_SQL = """
INSERT INTO market_quotes (symbol, label, value, change_pct, unit, decimals, sort_order, as_of)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (symbol) DO UPDATE
SET label = EXCLUDED.label, value = EXCLUDED.value, change_pct = EXCLUDED.change_pct,
    unit = EXCLUDED.unit, decimals = EXCLUDED.decimals, sort_order = EXCLUDED.sort_order,
    as_of = EXCLUDED.as_of, updated_at = now()
"""


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


async def _store(pool: asyncpg.Pool, item: Instrument, value: float, change: float | None,
                 as_of: datetime) -> None:
    await pool.execute(_UPSERT_SQL, item.symbol, item.label, value, change, item.unit,
                       item.decimals, item.sort_order, as_of)


async def refresh_quotes(pool: asyncpg.Pool, client: httpx.AsyncClient) -> int:
    updated = 0
    for item in INSTRUMENTS:
        try:
            response = await client.get(YAHOO_URL.format(symbol=quote(item.symbol, safe="")),
                                        params={"range": "1d", "interval": "1d"})
            response.raise_for_status()
            price, change, as_of = parse_chart(response.json())
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError,
                ZeroDivisionError) as exc:
            log.warning("quote %s unavailable: %r", item.symbol, exc)
            continue
        await _store(pool, item, price, change, as_of)
        updated += 1
    return updated


async def refresh_spread(pool: asyncpg.Pool) -> bool:
    rows = await pool.fetch(
        """SELECT title, summary, published_at FROM articles
           WHERE language = 'it' AND published_at > now() - interval '4 days'
             AND (title ILIKE '%spread%' OR summary ILIKE '%spread%')
           ORDER BY published_at DESC LIMIT 20""")
    for row in rows:
        value = parse_spread(row["title"]) or parse_spread(row["summary"])
        if value is not None:
            item = Instrument(SPREAD_SYMBOL, "Spread BTP/Bund", 0, "pb", 40)
            await _store(pool, item, float(value), None, row["published_at"])
            return True
    return False


async def fetch_markets(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """SELECT symbol, label, value, change_pct, unit, decimals, as_of FROM market_quotes
           WHERE as_of > now() - interval '7 days' ORDER BY sort_order""")
    return [{**dict(row), "as_of": row["as_of"].isoformat()} for row in rows]
