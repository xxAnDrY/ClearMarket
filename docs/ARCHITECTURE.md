# ClearMarkets: architettura

```mermaid
flowchart LR
  F[Feed RSS italiani ed esteri<br/>Finnhub, Yahoo] --> J[GitHub Actions<br/>ogni 15-60 minuti]
  J -->|state.json e JSON pubblici| D[Ramo data]
  D -->|proxy /live| N[Netlify]
  Y[Yahoo Finance] -->|/api/chart, /api/movers| N
  N --> B[Browser<br/>React]
```

Non ci sono database né processi sempre attivi. La memoria tra un giro e l'altro è `state.json`
sul ramo `data`, sovrascritto con un solo commit per non far crescere la cronologia. Il sito legge
`feed.json` e `markets.json` e filtra nel browser categorie e ricerca.

## Dashboard

Una sola pagina: barra mercati e ricerca in alto, feed a sinistra, grafico e market mover a destra
(sopra il feed su telefono). La ricerca universale filtra le notizie e suggerisce ETF e indici.

L'indicatore LIVE dipende dai dati: compare solo se l'ultimo scambio ha meno di 3 minuti. Con mercato
aperto e dato più vecchio il sito mostra "Ritardato". La precisione del grafico è quella delle barre
Yahoo (5 minuti in 1D), quindi i secondi del tooltip sono quelli della barra.

- **`/api/chart`:** serie storica di un simbolo per 1D, 1W, 1M, 1Y e ALL.
- **`/api/quote`:** ultima quotazione. La pagina la richiede ogni 15 secondi a mercato aperto e a
  scheda visibile; la CDN la condivide tra i visitatori per 10 secondi.
- **`/api/movers`:** le tre maggiori variazioni di oggi in un paniere fisso di grandi titoli, quindi
  non dell'intero mercato.
- **Catalogo:** ETF e indici cercabili sono elencati in `web/src/instruments.ts`.

Le funzioni accettano solo simboli e periodi validi. La CDN di Netlify conserva le risposte, così il
traffico non si trasforma in chiamate a Yahoo.

## Un giro

1. **Raccolta:** richieste condizionali con ETag, `minId` per Finnhub. Una fonte guasta non blocca le
   altre; dopo un 429 viene saltata fino a `Retry-After`.
2. **Normalizzazione:** testo pulito, estratto di 280 caratteri, ticker, categoria, sentiment.
3. **Deduplicazione:** URL canonica; stesso titolo entro 48 ore; titolo simile entro 12 ore con gli
   stessi numeri e nomi propri. I doppioni restano con `duplicate_of` e non vengono mostrati.
4. **Barra mercati:** quotazioni Yahoo e spread letto dalle notizie italiane.
5. **Pubblicazione:** ultimi 800 articoli; lo stato conserva 14 giorni.

## Cadenza

Il cron gira circa ogni 15 minuti nelle ore di mercato e ogni ora il resto del tempo. GitHub può
ritardare i job, quindi non è un servizio in tempo reale. Con un repository pubblico i minuti di
Actions sono gratuiti. GitHub può sospendere i job programmati dopo un lungo periodo senza attività
nel repository: in quel caso si riattivano dalla scheda Actions.

## Lingue e fonti

Le notizie restano nella lingua originale, con un badge IT o EN: non c'è traduzione. L'elenco delle
fonti è in `pipeline/clearmarkets/catalog.py`. Milano Finanza, Teleborsa e Reuters non espongono un
RSS pubblico funzionante e non facciamo scraping.

## Rischi

| Rischio | Dettaglio | Azione |
|---|---|---|
| **Licenze** | Titoli ed estratti di testate terze vengono ripubblicati su un sito pubblico e nel repository, con molte più fonti | Verifica legale per fonte prima di promuovere il sito |
| **Quotazioni** | Endpoint Yahoo non ufficiale, ritardato e senza licenza chiara; da GitHub o Netlify può essere bloccato. Lo spread si aggiorna solo con le notizie e non ha variazione | Fornitore a contratto |
| **Sentiment** | Lessico semplice, può sbagliare | Modello dedicato o rimozione |
| **Doppioni tra lingue** | Lo stesso fatto da fonte italiana ed estera appare due volte | Confronto semantico |
| **Normativa** | Il sito non è consulenza finanziaria | Parere legale prima di un lancio pubblico |
