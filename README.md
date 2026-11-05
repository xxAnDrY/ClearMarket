# ClearMarket

Sito web di notizie finanziarie in italiano: worker di ingestion e API in Python (FastAPI),
PostgreSQL, Redis e frontend React con Vite e Tailwind.

- Architettura e rischi aperti: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Messa online 24/7: [docs/DEPLOY.md](docs/DEPLOY.md)

```text
backend/    API, worker, traduzione, migrazioni SQL e test
web/        sito React e configurazione Caddy
deploy/     stack di produzione per un server
archive/    vecchia app Flutter, solo come riferimento
```

## Avvio in locale

Serve Docker. Copia `backend/.env.example` in `backend/.env`. Le chiavi sono facoltative: senza
`FINNHUB_API_KEY` le fonti Finnhub restano in backoff, senza `DEEPL_API_KEY` si usa la quota ridotta
di MyMemory.

```bash
docker compose up --build
```

Il sito è su `http://localhost:8080`. Le notizie compaiono entro un paio di minuti.

## Sviluppo del sito

Con il backend attivo su `127.0.0.1:8000`:

```bash
cd web && npm install && npm run dev
```

```bash
npm test && npm run build
```

## Test del backend

Serve un database usa-e-getta: lo schema viene cancellato e ricreato a ogni esecuzione.

```bash
cd backend && pip install -e ".[dev]"
```

```bash
TEST_DATABASE_URL=postgresql://clearmarket:clearmarket@localhost:5432/clearmarket_test pytest
```

## Aggiornare un database già creato

Le migrazioni vengono eseguite solo quando il volume Postgres è nuovo:

```bash
docker compose exec -T postgres psql -U clearmarket clearmarket < backend/migrations/003_italian_feed.sql
```

```bash
docker compose exec -T postgres psql -U clearmarket clearmarket < backend/migrations/004_market_quotes.sql
```
