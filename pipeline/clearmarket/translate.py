"""Traduzione in italiano di titolo e sommario degli articoli esteri.

Gli articoli esteri entrano nello stato come `pending` e non vengono pubblicati finche'
non sono tradotti: nel feed non compare mai testo in inglese. A ogni giro si traducono i piu'
recenti, entro un tetto giornaliero di caratteri che protegge le quote gratuite.
"""
import logging
from html import unescape
from typing import Any, Protocol

import httpx

log = logging.getLogger("clearmarket.translate")

TARGET = "it"
MAX_ATTEMPTS = 5
DEEPL_URL = "https://api-free.deepl.com/v2/translate"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
_MYMEMORY_MAX_BYTES = 500


class TranslationError(Exception):
    """Errore temporaneo: l'articolo resta in coda."""


class QuotaExceeded(TranslationError):
    """Quota esaurita: il backend non si usa piu' in questo giro."""


class Backend(Protocol):
    name: str
    daily_chars: int

    async def translate(self, texts: list[str], source: str) -> list[str]: ...


class DeepLBackend:
    """API ufficiale. Il piano Free richiede una chiave e ha una quota mensile."""
    name = "deepl"
    daily_chars = 15_000

    def __init__(self, client: httpx.AsyncClient, api_key: str, url: str = DEEPL_URL) -> None:
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
    """Nessuna chiave, ma quota giornaliera ridotta: adatto come riserva."""
    name = "mymemory"
    daily_chars = 4_500

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _one(self, text: str, source: str) -> str:
        query = text.encode()[:_MYMEMORY_MAX_BYTES].decode(errors="ignore")
        try:
            response = await self._client.get(MYMEMORY_URL, params={"q": query, "langpair": f"{source}|{TARGET}"})
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


def build_backends(client: httpx.AsyncClient, deepl_key: str | None) -> list[Backend]:
    backends: list[Backend] = [MyMemoryBackend(client)]
    if deepl_key:
        backends.insert(0, DeepLBackend(client, deepl_key))
    return backends


async def translate_pending(
    articles: list[dict[str, Any]], backends: list[Backend], budget: dict[str, Any], today: str,
) -> int:
    """Traduce i piu' recenti in coda e aggiorna gli articoli sul posto."""
    if budget.get("day") != today:
        budget.clear()
        budget.update(day=today, chars=0)
    available = list(backends)
    done = 0
    queue = [article for article in articles if article["translation_status"] == "pending"]
    for article in sorted(queue, key=lambda item: item["published_at"], reverse=True):
        texts = [article["title_original"]]
        if article["summary_original"]:
            texts.append(article["summary_original"])
        cost = sum(map(len, texts))
        available = [backend for backend in available if budget["chars"] + cost <= backend.daily_chars]
        if not available:
            break
        for backend in list(available):
            try:
                translated = await backend.translate(texts, article["language"])
            except QuotaExceeded as exc:
                log.warning("%s stopped: %s", backend.name, exc)
                available.remove(backend)
            except TranslationError as exc:
                log.warning("%s failed: %s", backend.name, exc)
            else:
                if len(translated) == len(texts) and all(item.strip() for item in translated):
                    article["title"] = translated[0]
                    article["summary"] = translated[1] if len(translated) > 1 else ""
                    article["translated_by"] = backend.name
                    article["translation_status"] = "done"
                    budget["chars"] += cost
                    done += 1
                    break
        else:
            if available:  # ogni backend attivo ha fallito su questo articolo
                article["translation_attempts"] += 1
                if article["translation_attempts"] >= MAX_ATTEMPTS:
                    article["translation_status"] = "failed"
    return done
