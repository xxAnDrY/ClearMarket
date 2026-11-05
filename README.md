# ClearMarket

MVP di un feed aggregato di notizie finanziarie: worker di ingestion e API in Python
(FastAPI), PostgreSQL, Redis e app Flutter con Riverpod.

Architettura, rate limit, deduplicazione, FCM, offline-first e rischi aperti:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Messa online 24/7: [docs/DEPLOY.md](docs/DEPLOY.md).

```text
backend/
  migrations/          schema SQL e seed di categorie e fonti
  app/ingestion/       worker, adapter delle fonti, normalizzazione, deduplicazione
  app/main.py          API
  app/cache.py         cache Redis con anti-stampede e copia stale
  app/ratelimit.py     token bucket e limite in ingresso
  tests/               test su Postgres reale
mobile/
  lib/features/feed/   ArticleModel, FeedController, FeedView, ArticleCard, skeleton
  lib/features/watchlist/, lib/features/calendar/
```

## Avvio del backend

Serve Docker. Copia `backend/.env.example` in `backend/.env`, imposta `JWT_SECRET` e, se ne
hai una, `FINNHUB_API_KEY`. Senza chiave le fonti Finnhub restano in backoff, mentre RSS e
calendario funzionano. Per tradurre davvero le fonti estere imposta anche `DEEPL_API_KEY`.

```bash
docker compose up --build
```

```bash
curl "http://localhost:8000/api/v1/feed?scope=top&limit=5"
```

Documentazione interattiva su `http://localhost:8000/docs`.

## Test del backend

Serve un database usa-e-getta: lo schema viene cancellato e ricreato a ogni esecuzione.

```bash
cd backend && pip install -e ".[dev]"
```

```bash
TEST_DATABASE_URL=postgresql://clearmarket:clearmarket@localhost:5432/clearmarket_test pytest
```

## Installare l'app su un telefono

Il telefono deve raggiungere il backend. In locale PC e telefono devono stare sulla stessa
rete Wi-Fi e il backend deve essere attivo (`docker compose up`).

**1. Configura l'indirizzo.** Trova l'IP del PC con `ipconfig` (voce IPv4), poi crea
`mobile/config/dev.json` partendo da `dev.json.example`. Il file non va condiviso, perche'
contiene il token di sviluppo.

```bash
cd backend && python scripts/mint_dev_token.py
```

**2. Apri la porta 8000 sul PC** una volta sola, da PowerShell come amministratore:

```bash
New-NetFirewallRule -DisplayName "ClearMarket API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

**3. Prova la connessione** aprendo dal browser del telefono `http://<IP-DEL-PC>:8000/healthz`.

**4. Android.** Con il telefono collegato via USB e il debug USB attivo:

```bash
cd mobile && flutter pub get
```

```bash
flutter run --dart-define-from-file=config/dev.json
```

Per generare un file da installare:

```bash
flutter build apk --debug --dart-define-from-file=config/dev.json
```

```bash
adb install -r build/app/outputs/flutter-apk/app-debug.apk
```

Il file si puo' anche copiare sul telefono e aprire, consentendo l'installazione da app sconosciute.

**Build release.** `flutter build apk --release --dart-define=API_BASE_URL=https://api.tuodominio.it`
richiede un backend in HTTPS, perche' Android blocca l'HTTP fuori dal debug, e una chiave di firma
propria prima di andare sugli store.

**5. iOS.** Serve un Mac con Xcode. Apri `mobile/ios/Runner.xcworkspace`, scegli il tuo team in
Signing & Capabilities, collega l'iPhone e lancia:

```bash
flutter run --release --dart-define-from-file=config/dev.json
```

La prima volta iOS chiede il permesso per la rete locale: va concesso.

**Emulatore Android.** Usa `http://10.0.2.2:8000` come `API_BASE_URL`.

## Aggiornare un database gia' creato

Le migrazioni vengono eseguite solo quando il volume Postgres e' nuovo:

```bash
docker compose exec -T postgres psql -U clearmarket clearmarket < backend/migrations/003_italian_feed.sql
```

## Supabase in produzione

Attiva gli accessi anonimi, passa `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` al posto di
`DEV_JWT` e imposta `JWT_JWKS_URL` sul backend. Prima di pubblicare sostituisci l'identificativo
provvisorio `com.clearmarket.clearmarket`.
