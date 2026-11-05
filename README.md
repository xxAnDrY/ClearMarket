# ClearMarkets

Dashboard di notizie finanziarie in italiano, con grafici di ETF e indici, senza server: un job di
GitHub Actions raccoglie e traduce le notizie, Netlify pubblica il sito React e due funzioni leggere.

```text
pipeline/            raccolta, deduplica, traduzione e scrittura dei JSON (Python)
web/                 dashboard React con Vite e Tailwind
web/netlify/         funzioni per grafici e market mover
.github/workflows/   job programmato
```

Architettura e limiti: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Messa online

1. Su Netlify collega questo repository: `netlify.toml` contiene già tutte le impostazioni.
2. Tieni pubblico il repository: il sito legge i dati dal ramo `data`, che da privato non è raggiungibile.
3. In GitHub > Settings > Secrets and variables > Actions aggiungi `DEEPL_API_KEY` e, se vuoi,
   `FINNHUB_API_KEY`. Sono facoltative.
4. In GitHub > Actions apri **Aggiorna dati** e lancia **Run workflow**.

## Sviluppo

```bash
cd web && npm install && npm run dev
```

```bash
npm test && npm run build
```

```bash
cd pipeline && pip install -e ".[dev]" && pytest
```

Per provare un giro in locale:

```bash
cd pipeline && python -m clearmarkets.run --out ../.data-local
```
