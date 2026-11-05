"""Da record grezzi di provider diversi allo schema unico `NormalizedArticle`."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser

from app.ingestion.dedupe import canonicalize_url, title_hash, url_hash

SUMMARY_MAX_CHARS = 280  # solo un estratto: il testo completo resta all'editore
_MAX_FUTURE_SKEW = timedelta(minutes=5)


@dataclass(slots=True)
class RawArticle:
    """Output di un adapter: i campi mancanti vengono completati da `normalize`."""
    title: str
    url: str
    summary: str = ""
    published_at: datetime | None = None
    tickers: tuple[str, ...] = ()


@dataclass(slots=True)
class NormalizedArticle:
    source_id: int
    category: str
    title: str
    summary: str
    url: str
    published_at: datetime
    related_tickers: list[str]
    sentiment: str
    sentiment_score: float
    url_hash: bytes = field(repr=False)
    title_hash: bytes = field(repr=False)
    language: str = "it"
    title_original: str = ""
    summary_original: str = ""
    translation_status: str = "not_needed"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.chunks.append(data)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    extractor = _TextExtractor()
    extractor.feed(value)
    extractor.close()
    # Alcuni feed fanno doppio escape ("&amp;amp;"): unescape copre il secondo giro.
    return " ".join(unescape("".join(extractor.chunks)).split())


def truncate(text: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"


# --- Ticker ---------------------------------------------------------------------
# Alias testuali -> ticker. I titoli dicono "Nvidia", non "NVDA". La chiave e' cercata
# a parola intera e senza distinzione di maiuscole, quindi evitare alias ambigui.
TICKER_ALIASES: dict[str, str] = {
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "amazon": "AMZN",
    "alphabet": "GOOGL", "google": "GOOGL", "meta platforms": "META", "tesla": "TSLA",
    "broadcom": "AVGO", "berkshire hathaway": "BRK.B", "jpmorgan": "JPM",
    "goldman sachs": "GS", "morgan stanley": "MS", "bank of america": "BAC",
    "exxon": "XOM", "netflix": "NFLX", "palantir": "PLTR", "intel": "INTC", "amd": "AMD",
    # UE, in formato ticker.borsa (Yahoo)
    "asml": "ASML.AS", "sap": "SAP.DE", "lvmh": "MC.PA", "siemens": "SIE.DE",
    "totalenergies": "TTE.PA", "airbus": "AIR.PA", "novo nordisk": "NOVO-B.CO",
    "nestle": "NESN.SW", "allianz": "ALV.DE", "unicredit": "UCG.MI",
    "intesa sanpaolo": "ISP.MI", "enel": "ENEL.MI", "eni": "ENI.MI",
    "ferrari": "RACE.MI", "stellantis": "STLA.MI", "assicurazioni generali": "G.MI",
    "mediobanca": "MB.MI", "banco bpm": "BAMI.MI", "monte dei paschi": "BMPS.MI",
    "poste italiane": "PST.MI", "prysmian": "PRY.MI", "snam": "SRG.MI",
    # Indici/ETF piu' citati
    "s&p 500": "SPY", "nasdaq 100": "QQQ",
    # Crypto
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "xrp": "XRP",
}
_ALIAS_RE = re.compile(
    r"(?<![\w&])(" + "|".join(re.escape(alias) for alias in
                              sorted(TICKER_ALIASES, key=len, reverse=True)) + r")(?![\w&])",
    re.IGNORECASE,
)
# $AAPL, $BTC. Esclude importi come "$100" richiedendo una lettera iniziale.
_CASHTAG_RE = re.compile(r"(?<![\w$])\$([A-Z][A-Z0-9.]{0,9})\b")
# (NASDAQ: AAPL), NYSE:JPM
_EXCHANGE_RE = re.compile(r"\b(?:NASDAQ|NYSE|AMEX|LSE|XETRA)\s*:\s*([A-Z][A-Z0-9.]{0,9})\b")


def extract_tickers(text: str, known: tuple[str, ...] = ()) -> list[str]:
    found = dict.fromkeys(ticker.upper() for ticker in known if ticker)
    found.update(dict.fromkeys(_CASHTAG_RE.findall(text)))
    found.update(dict.fromkeys(_EXCHANGE_RE.findall(text)))
    for match in _ALIAS_RE.finditer(text):
        found[TICKER_ALIASES[match.group(1).lower()]] = None
    return list(found)[:10]


# --- Categoria ------------------------------------------------------------------
# Ordine: dal tema piu' specifico al piu' generale. Termini inglesi e italiani insieme,
# perche' le regole girano sul testo originale di ogni fonte.
_CATEGORY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("crypto", re.compile(
        r"\b(bitcoin|ethereum|crypto\w*|cripto\w*|stablecoins?|blockchain|solana)\b", re.I)),
    ("monetary_policy", re.compile(
        r"\b(fed|fomc|ecb|bce|powell|lagarde|central banks?|rate (?:cut|hike|decision)s?|"
        r"interest rates?|monetary policy|federal reserve|quantitative (?:easing|tightening)|"
        r"banca centrale|banche centrali|politica monetaria|tassi di interesse|"
        r"(?:taglio|taglia|rialzo|aumento) (?:dei )?tassi)\b", re.I)),
    ("etf", re.compile(r"\b(etfs?|index funds?|ucits|fondi indicizzati)\b", re.I)),
    ("commodities", re.compile(
        r"\b(oil prices?|crude|brent|wti|opec|gold prices?|natural gas|copper|commodit\w+|"
        r"petrolio|greggio|oro|gas naturale|rame|materie prime)\b", re.I)),
    ("bonds", re.compile(
        r"\b(treasury yields?|bond yields?|bonds?|treasuries|gilts?|btp|bot|bund|spread|"
        r"obbligazioni\w*|titoli di stato|rendimenti)\b", re.I)),
    ("fiscal_policy", re.compile(
        r"\b(tariffs?|fiscal policy|government spending|budget deficit|tax (?:bill|cuts?|plan)|"
        r"manovra|legge di bilancio|governo|dazi|fisco|tasse|giorgetti|mef|"
        r"pnrr|ministro dell.economia|debito pubblico)\b", re.I)),
    ("macro", re.compile(
        r"\b(inflation|cpi|ppi|gdp|recession|unemployment|payrolls?|jobs report|pmi|"
        r"trade deficit|inflazione|pil|recessione|disoccupazione|occupazione|istat|"
        r"produzione industriale|bilancia commerciale)\b", re.I)),
    ("microeconomics", re.compile(
        r"\b(consumer spending|household\w*|wages?|retail sales|rents?|mortgages?|"
        r"consumi|famiglie|salari|stipendi|mutui|affitti|caro.?(?:vita|bollette))\b", re.I)),
    ("stocks_eu", re.compile(
        r"\b(stoxx|dax|cac 40|ftse|ftse mib|euronext|european (?:stocks|shares)|"
        r"piazza affari|borsa di milano|borse europee)\b", re.I)),
    ("stocks_us", re.compile(r"\b(wall street|s&p 500|dow jones|nasdaq|earnings)\b", re.I)),
)
_EU_TICKER_SUFFIXES = (".AS", ".DE", ".PA", ".MI", ".SW", ".CO", ".MC", ".L")


def classify(text: str, tickers: list[str], default: str, lock_default: bool = False) -> str:
    """Regole ordinate per specificita'. `lock_default` per fonti monotematiche."""
    if lock_default:
        return default
    for category, pattern in _CATEGORY_RULES:
        if pattern.search(text):
            return category
    if any(ticker.endswith(_EU_TICKER_SUFFIXES) for ticker in tickers):
        return "stocks_eu"
    return default


# --- Sentiment ------------------------------------------------------------------
# Lessico finanziario minimo per l'MVP: euristica sul titolo, non una previsione.
# Pesi piu' alti per i termini che raramente cambiano segno col contesto.
_POSITIVE = {
    "beat": 1, "beats": 1, "surge": 2, "surges": 2, "soar": 2, "soars": 2, "rally": 2,
    "rallies": 2, "gain": 1, "gains": 1, "jump": 1, "jumps": 1, "rise": 1, "rises": 1,
    "record": 1, "upgrade": 2, "upgraded": 2, "outperform": 2, "profit": 1, "growth": 1,
    "rebound": 1, "rebounds": 1, "strong": 1, "boost": 1, "boosts": 1, "bullish": 2,
    "optimism": 1, "recovery": 1,
    # Italiano. "sale" manca di proposito: in inglese significa "vendita".
    "balzo": 2, "balza": 2, "vola": 2, "volano": 2, "impennata": 2, "rimbalzo": 2,
    "rialzo": 1, "rialzi": 1, "salgono": 1, "crescita": 1, "cresce": 1, "crescono": 1,
    "utile": 1, "utili": 1, "ripresa": 1, "guadagna": 1, "guadagnano": 1, "promosso": 2,
}
_NEGATIVE = {
    "miss": 1, "misses": 1, "plunge": 2, "plunges": 2, "tumble": 2, "tumbles": 2,
    "crash": 2, "crashes": 2, "slump": 2, "slumps": 2, "fall": 1, "falls": 1, "drop": 1,
    "drops": 1, "sink": 1, "sinks": 1, "loss": 1, "losses": 1, "downgrade": 2,
    "downgraded": 2, "bankruptcy": 3, "default": 2, "fraud": 3, "lawsuit": 1, "probe": 1,
    "layoffs": 2, "recession": 2, "weak": 1, "fears": 1, "bearish": 2, "selloff": 2,
    "sell-off": 2, "warning": 1, "warns": 1,
    "crollo": 2, "crolla": 2, "crollano": 2, "tonfo": 2, "ribasso": 1, "ribassi": 1,
    "calo": 1, "cala": 1, "calano": 1, "scende": 1, "scendono": 1, "perde": 1, "perdono": 1,
    "perdita": 1, "perdite": 1, "crisi": 2, "fallimento": 3, "recessione": 2, "frode": 3,
    "licenziamenti": 2, "allarme": 1, "debole": 1, "bocciato": 2,
}
_NEGATORS = {"no", "not", "never", "without", "fail", "fails", "failed", "non", "senza"}
_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)?")


def score_sentiment(title: str, summary: str = "") -> tuple[str, float]:
    """Punteggio in [-1, 1] pesato sul titolo; l'etichetta richiede un segnale netto."""
    def tally(text: str, weight: int) -> tuple[int, int]:
        positive = negative = 0
        words = _WORD.findall(text.lower())
        for index, word in enumerate(words):
            # Due parole indietro: "fails to rally", "not a record".
            sign = -1 if _NEGATORS.intersection(words[max(0, index - 2):index]) else 1
            value = (_POSITIVE.get(word, 0) - _NEGATIVE.get(word, 0)) * sign * weight
            if value > 0:
                positive += value
            else:
                negative -= value
        return positive, negative

    title_pos, title_neg = tally(title, 2)
    summary_pos, summary_neg = tally(summary, 1)
    positive, negative = title_pos + summary_pos, title_neg + summary_neg
    if positive + negative == 0:
        return "neutral", 0.0
    score = round((positive - negative) / (positive + negative + 2), 3)
    if score >= 0.25:
        return "positive", score
    if score <= -0.25:
        return "negative", score
    return "neutral", score


# --- Pipeline -------------------------------------------------------------------
def normalize(
    raw: RawArticle,
    *,
    source_id: int,
    default_category: str,
    lock_category: bool = False,
    language: str = "it",
    now: datetime | None = None,
) -> NormalizedArticle | None:
    """Restituisce None per i record inutilizzabili, senza interrompere il batch."""
    now = now or datetime.now(timezone.utc)
    title = clean_text(raw.title)
    url = raw.url.strip()
    # Il link finisce in url_launcher: niente javascript:, intent:, data:.
    if not title or not url.lower().startswith(("http://", "https://")):
        return None

    summary = truncate(clean_text(raw.summary))
    if summary.lower() == title.lower():
        summary = ""

    # Una data futura terrebbe l'articolo in cima al feed per ore; una assente
    # equivale a "appena visto".
    published_at = raw.published_at or now
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if published_at > now + _MAX_FUTURE_SKEW:
        published_at = now

    # Ticker, categoria e sentiment usano sempre il testo originale.
    text = f"{title}. {summary}"
    tickers = extract_tickers(text, raw.tickers)
    label, score = score_sentiment(title, summary)
    canonical = canonicalize_url(url)
    return NormalizedArticle(
        source_id=source_id,
        category=classify(text, tickers, default_category, lock_category),
        title=title,
        summary=summary,
        url=canonical,
        published_at=published_at,
        related_tickers=tickers,
        sentiment=label,
        sentiment_score=score,
        url_hash=url_hash(canonical),
        title_hash=title_hash(title),
        language=language,
        title_original=title,
        summary_original=summary,
        translation_status="not_needed" if language == "it" else "pending",
    )
