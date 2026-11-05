import { useState, type FormEvent } from "react";
import { CATEGORIES } from "../api";
import { normalizeTicker, useWatchlist } from "../preferences";
import { NewsCardGrid } from "./NewsCardGrid";

export function WatchlistPage({ onTicker }: { onTicker: (ticker: string) => void }) {
  const [watchlist, save] = useWatchlist();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState(false);

  const addTicker = (event: FormEvent) => {
    event.preventDefault();
    const ticker = normalizeTicker(draft);
    setError(ticker === null);
    if (!ticker) return;
    setDraft("");
    if (!watchlist.tickers.includes(ticker)) save({ ...watchlist, tickers: [...watchlist.tickers, ticker] });
  };

  const toggleCategory = (slug: string) =>
    save({
      ...watchlist,
      categories: watchlist.categories.includes(slug)
        ? watchlist.categories.filter((item) => item !== slug)
        : [...watchlist.categories, slug],
    });

  const isEmpty = watchlist.tickers.length === 0 && watchlist.categories.length === 0;

  return (
    <section aria-label="Watchlist">
      <div className="mb-3 rounded-2xl border border-line bg-surface p-4 shadow-sm">
        <form onSubmit={addTicker} className="flex gap-2">
          <input
            value={draft}
            onChange={(event) => { setDraft(event.target.value); setError(false); }}
            aria-label="Aggiungi ticker"
            aria-invalid={error}
            placeholder="Ticker, es. AAPL, BTC, UCG.MI"
            className="min-w-0 flex-1 rounded-full bg-raised px-4 py-2 text-sm outline-none placeholder:text-muted focus:ring-2 focus:ring-accent/40"
          />
          <button className="tactile rounded-full bg-accent px-4 py-2 text-sm font-semibold text-on-accent">Aggiungi</button>
        </form>
        {error && <p className="mt-1 text-xs text-down">Ticker non valido.</p>}
        {watchlist.tickers.length > 0 && (
          <ul className="mt-2.5 flex flex-wrap gap-1.5">
            {watchlist.tickers.map((ticker) => (
              <li key={ticker}>
                <button
                  aria-label={`Rimuovi ${ticker}`}
                  onClick={() => save({ ...watchlist, tickers: watchlist.tickers.filter((item) => item !== ticker) })}
                  className="tactile rounded-full bg-raised px-2.5 py-1 text-xs font-semibold tabular-nums hover:text-down"
                >
                  {ticker} ×
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {Object.entries(CATEGORIES).map(([slug, label]) => (
            <button
              key={slug}
              aria-pressed={watchlist.categories.includes(slug)}
              onClick={() => toggleCategory(slug)}
              className="tactile rounded-full bg-raised px-3 py-1.5 text-xs font-medium text-muted hover:text-text aria-pressed:bg-accent aria-pressed:font-semibold aria-pressed:text-on-accent"
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted">Salvata solo in questo browser.</p>
      </div>
      {isEmpty ? (
        <p className="rounded-2xl border border-line bg-surface px-4 py-16 text-center text-muted shadow-sm">Segui ticker e categorie per costruire il tuo feed.</p>
      ) : (
        <NewsCardGrid query={{ kind: "watchlist", ...watchlist }} onTicker={onTicker} />
      )}
    </section>
  );
}
