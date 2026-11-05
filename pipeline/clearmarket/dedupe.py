"""Fingerprint per la deduplicazione.

La deduplicazione lavora su tre livelli, dal piu' certo al piu' euristico:

  L1  url_hash    SHA-256 della URL canonica: il duplicato non viene aggiunto.
  L2  title_hash  SHA-256 del titolo normalizzato, confrontato solo entro 48 ore: "Fed holds
                  rates steady" torna ogni qualche mese ed e' una notizia nuova.
  L3  trigrammi   similarita' sul titolo entro 12 ore, solo con la stessa firma (numeri e nomi
                  propri). I trigrammi da soli fonderebbero Fed ed ECB nello stesso titolo.

L2 e L3 non scartano: tengono l'articolo con `duplicate_of` e il sito non lo mostra.
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


def _trigrams(text: str) -> set[str]:
    grams: set[str] = set()
    for word in re.findall(r"\w+", text.lower()):
        padded = f"  {word} "
        grams.update(padded[index:index + 3] for index in range(len(padded) - 2))
    return grams


def trigram_similarity(first: str, second: str) -> float:
    """Jaccard sui trigrammi di parola, come `similarity()` di pg_trgm."""
    a, b = _trigrams(first), _trigrams(second)
    return len(a & b) / len(a | b) if a and b else 0.0
