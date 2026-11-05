"""Fingerprint per la deduplicazione.

La deduplicazione lavora su tre livelli, dal piu' certo al piu' euristico:

  L1  url_hash    SHA-256 della URL canonica. Vincolo UNIQUE: il duplicato non
                  viene inserito. Copre i re-fetch dello stesso feed.
  L2  title_hash  SHA-256 del titolo normalizzato, confrontato solo in una finestra
                  temporale: "Fed holds rates steady" torna ogni qualche mese ed
                  e' una notizia nuova. Copre la syndication tra testate.
  L3  pg_trgm     similarita' sul titolo in una finestra breve, solo se i titoli hanno la
                  stessa firma (numeri e nomi propri). I trigrammi da soli considerano
                  uguali "Fed holds rates steady" e "ECB holds rates steady".

L2 e L3 non scartano: salvano la riga con `duplicate_of` e il feed la nasconde. Un
falso positivo e' quindi reversibile con una UPDATE.
"""
import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = frozenset({
    "fbclid", "gclid", "dclid", "msclkid", "igshid", "mc_cid", "mc_eid",
    "ref", "ref_src", "cmpid", "ocid", "soc_src", "soc_trk", "smid", "yptr", "__source",
})
_TRACKING_PREFIXES = ("utm_", "at_", "trk_")
_OUTLET_SUFFIX = re.compile(r"\s+[-–—|]\s+[^-–—|]{2,30}$")
_SIGNATURE_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_][\w'’-]*")


def canonicalize_url(url: str) -> str:
    """URL senza tracking e frammento: e' il link salvato, quindi deve restare navigabile."""
    parts = urlsplit(url.strip())
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
        and not key.lower().startswith(_TRACKING_PREFIXES)
    )
    path = re.sub(r"/{2,}", "/", parts.path)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def url_hash(canonical_url: str) -> bytes:
    # Solo per il confronto, non per il link: schema, "www." e slash finale non
    # distinguono due articoli, ma toglierli dalla URL salvata puo' romperla.
    parts = urlsplit(canonical_url)
    key = parts.netloc.removeprefix("www.") + parts.path.rstrip("/") + "?" + parts.query
    return hashlib.sha256(key.encode()).digest()


def normalize_title(title: str) -> str:
    """Minuscolo, senza accenti, punteggiatura o suffissi di testata (' - Reuters')."""
    text = unicodedata.normalize("NFKD", _OUTLET_SUFFIX.sub("", title))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return " ".join(re.sub(r"[^\w\s%.]", " ", text).split())


def title_hash(title: str) -> bytes:
    return hashlib.sha256(normalize_title(title).encode()).digest()


def title_signature(title: str) -> frozenset[str]:
    """Numeri e parole con iniziale maiuscola: cio' che distingue due notizie simili.

    Sui titoli in Title Case la firma e' piu' severa e L3 scatta meno spesso: e' il
    verso sicuro, perche' un doppione visibile costa meno di una notizia nascosta.
    """
    tokens = _SIGNATURE_TOKEN.findall(_OUTLET_SUFFIX.sub("", title))
    return frozenset(token.lower() for token in tokens if not token[0].islower())
