# ClearMarket

Sito di notizie finanziarie in italiano, senza server: un job di GitHub Actions raccoglie e traduce
le notizie, Netlify pubblica il sito React.

```text
pipeline/            raccolta, deduplica, traduzione e scrittura dei JSON (Python)
web/                 sito React con Vite e Tailwind
.github/workflows/   job programmato
archive/             vecchia app Flutter, solo come riferimento
```

Architettura e limiti: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Messa online

1. Su Netlify collega questo repository: `netlify.toml` contiene già tutte le impostazioni.
2. Rendi pubblico il repository (GitHub > Settings > General > Danger Zone). Con un repository
   privato il sito non riceve gli aggiornamenti e mostra l'istantanea in `web/public/data`.
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

Per generare i dati in locale e aggiornare l'istantanea del sito:

```bash
cd pipeline && python -m clearmarket.run --out ../.data-local
```
