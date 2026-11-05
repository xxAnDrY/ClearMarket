"""Traduzione asincrona in italiano di titolo e sommario degli articoli esteri.

Il worker salva subito l'articolo con stato `pending`, nascosto dal feed, e questo modulo
lo traduce a parte. Tradurre prima dell'INSERT perderebbe gli articoli quando il servizio
e' giu': dopo un 304 il feed non li riproporrebbe.

I backend si provano in ordine. Con quota finita un backend va in pausa; se non ne resta
nessuno gli articoli attendono, senza mai apparire in inglese.
"""
import logging
import time
from html import unescape
from typing import Protocol

import asyncpg
import httpx

from app.config import Settings

log = logging.getLogger("clearmarket.translate")

TARGET = "it"
MAX_ATTEMPTS = 5
_LEASE_S = 120.0
_QUOTA_PAUSE_S = 3600.0
_MYMEMORY_MAX_BYTES = 500

_CLAIM_SQL = """
UPDATE articles SET translate_after = now() + make_interval(secs => $2)
WHERE id IN (
    SELECT id FROM articles
    WHERE translation_status = 'pending' AND translate_after <= now()
    ORDER BY published_at DESC
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, language, title_original, summary_original, translation_attempts
"""


class TranslationError(Exception):
    """Errore temporaneo: l'articolo resta in coda."""


class QuotaExceeded(TranslationError):
    """Quota esaurita o limite raggiunto: il backend va in pausa."""


class Backend(Protocol):
    name: str

    async def translate(self, texts: list[str], source: str) -> list[str]: ...


class DeepLBackend:
    """API ufficiale. Il piano Free richiede una chiave e include una quota mensile."""
    name = "deepl"

    def __init__(self, client: httpx.AsyncClient, api_key: str, url: str) -> None:
        self._client = client
        self._api_key = api_key
        self._url = url

    async def translate(self, texts: list[str], source: str) -> list[str]:
        try:
            response = await self._client.post(
                self._url,
                headers={"Authorization": f"DeepL-Auth-Key {self._api_key}"},
                json={"text": texts, "source_lang": source.upper(), "target_lang": "IT"},
            )
        except httpx.HTTPError as exc:
            raise TranslationError(repr(exc)) from exc
        if response.status_code in (429, 456):  # 456: quota mensile finita
            raise QuotaExceeded(f"deepl {response.status_code}")
        if response.status_code != 200:
            raise TranslationError(f"deepl {response.status_code}")
        return [item["text"] for item in response.json()["translations"]]


class MyMemoryBackend:
    """Nessuna chiave, ma quota giornaliera ridotta: adatto a sviluppo e riserva."""
    name = "mymemory"
    URL = "https://api.mymemory.translated.net/get"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _one(self, text: str, source: str) -> str:
        query = text.encode()[:_MYMEMORY_MAX_BYTES].decode(errors="ignore")
        try:
            response = await self._client.get(
                self.URL, params={"q": query, "langpair": f"{source}|{TARGET}"})
        except httpx.HTTPError as exc:
            raise TranslationError(repr(exc)) from exc
        if response.status_code == 429:
            raise QuotaExceeded("mymemory 429")
        if response.status_code != 200:
            raise TranslationError(f"mymemory {response.status_code}")
        payload = response.json()
        translated = unescape(payload["responseData"]["translatedText"] or "").strip()
        # A quota finita risponde 200 e mette l'avviso al posto della traduzione.
        if "MYMEMORY WARNING" in translated or str(payload.get("responseStatus")) in ("403", "429"):
            raise QuotaExceeded("mymemory quota")
        if str(payload.get("responseStatus")) != "200" or not translated:
            raise TranslationError(f"mymemory status {payload.get('responseStatus')}")
        return translated

    async def translate(self, texts: list[str], source: str) -> list[str]:
        return [await self._one(text, source) for text in texts]


def build_backends(settings: Settings, client: httpx.AsyncClient) -> list[Backend]:
    backends: list[Backend] = []
    for name in settings.translation_backends.split(","):
        name = name.strip()
        if name == "deepl" and settings.deepl_api_key:
            backends.append(DeepLBackend(client, settings.deepl_api_key, settings.deepl_api_url))
        elif name == "mymemory":
            backends.append(MyMemoryBackend(client))
    return backends


class TranslationQueue:
    def __init__(self, pool: asyncpg.Pool, backends: list[Backend], batch: int) -> None:
        self._pool = pool
        self._backends = backends
        self._batch = batch
        self._paused_until: dict[str, float] = {}

    def _available(self) -> list[Backend]:
        now = time.monotonic()
        return [backend for backend in self._backends
                if self._paused_until.get(backend.name, 0) <= now]

    async def _translate(self, texts: list[str], source: str) -> tuple[list[str], str]:
        last_error: Exception = TranslationError("no backend available")
        for backend in self._available():
            try:
                result = await backend.translate(texts, source)
            except QuotaExceeded as exc:
                log.warning("%s paused: %s", backend.name, exc)
                self._paused_until[backend.name] = time.monotonic() + _QUOTA_PAUSE_S
                last_error = exc
            except TranslationError as exc:
                log.warning("%s failed: %s", backend.name, exc)
                last_error = exc
            else:
                if len(result) == len(texts) and all(item.strip() for item in result):
                    return result, backend.name
                last_error = TranslationError(f"{backend.name}: malformed response")
        raise last_error

    async def run_once(self) -> int:
        """Traduce un lotto e restituisce quanti articoli sono diventati visibili."""
        if not self._available():
            return 0
        rows = await self._pool.fetch(_CLAIM_SQL, self._batch, _LEASE_S)
        done = 0
        for row in rows:
            texts = [row["title_original"]]
            if row["summary_original"]:
                texts.append(row["summary_original"])
            try:
                translated, backend = await self._translate(texts, row["language"])
            except QuotaExceeded:
                # Non e' colpa dell'articolo: niente tentativo consumato.
                continue
            except TranslationError:
                attempts = row["translation_attempts"] + 1
                await self._pool.execute(
                    """UPDATE articles SET translation_attempts = $2::smallint,
                           translation_status = CASE WHEN $2::smallint >= $3::smallint
                                                     THEN 'failed' ELSE 'pending' END
                       WHERE id = $1""", row["id"], attempts, MAX_ATTEMPTS)
                continue
            await self._pool.execute(
                """UPDATE articles SET title = $2, summary = $3, translated_by = $4,
                       translation_status = 'done'
                   WHERE id = $1""",
                row["id"], translated[0], translated[1] if len(translated) > 1 else "", backend)
            done += 1
        return done
