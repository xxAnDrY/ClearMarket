"""Frequenza di polling legata agli orari di mercato.

Il tempo reale puro consumerebbe i limiti delle API gratuite senza vantaggi: di notte e
nel weekend le notizie finanziarie sono poche. Le festivita' di borsa non sono gestite e
contano come giorni aperti: costano solo qualche chiamata in piu'.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
MARKET_OPEN = time(8, 30)
MARKET_CLOSE = time(22, 30)
_MIN_DELAY_S = 30.0
_SATURDAY = 5


def is_market_open(now: datetime) -> bool:
    local = now.astimezone(ROME)
    return local.weekday() < _SATURDAY and MARKET_OPEN <= local.time() < MARKET_CLOSE


def next_market_open(now: datetime) -> datetime:
    local = now.astimezone(ROME)
    day = local.date()
    if local.time() >= MARKET_OPEN:
        day += timedelta(days=1)
    while day.weekday() >= _SATURDAY:
        day += timedelta(days=1)
    # Costruita dal calendario locale, cosi' il cambio dell'ora non la sposta.
    return datetime.combine(day, MARKET_OPEN, tzinfo=ROME)


def next_poll_delay(now: datetime, open_interval_s: float, closed_interval_s: float) -> float:
    """Secondi al prossimo polling. A mercato chiuso non scavalca mai l'apertura."""
    if is_market_open(now):
        return open_interval_s
    until_open = (next_market_open(now) - now).total_seconds()
    return max(min(closed_interval_s, until_open), _MIN_DELAY_S)
