import { useCallback, useState } from "react";

// Lo storage puo' mancare (navigazione privata): le preferenze restano solo in memoria.
function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* nessuna persistenza disponibile */
  }
}

export interface Watchlist {
  tickers: string[];
  categories: string[];
}

const WATCHLIST_KEY = "clearmarket.watchlist";
const THEME_KEY = "clearmarket.theme";
const TICKER = /^[A-Z0-9][A-Z0-9.-]{0,14}$/;

export function normalizeTicker(raw: string): string | null {
  const ticker = raw.trim().toUpperCase().replace(/^\$/, "");
  return TICKER.test(ticker) ? ticker : null;
}

function loadWatchlist(): Watchlist {
  try {
    const parsed = JSON.parse(read(WATCHLIST_KEY) ?? "{}") as Partial<Watchlist>;
    return {
      tickers: Array.isArray(parsed.tickers) ? parsed.tickers : [],
      categories: Array.isArray(parsed.categories) ? parsed.categories : [],
    };
  } catch {
    return { tickers: [], categories: [] };
  }
}

export function useWatchlist() {
  const [watchlist, setWatchlist] = useState(loadWatchlist);
  const save = useCallback((next: Watchlist) => {
    write(WATCHLIST_KEY, JSON.stringify(next));
    setWatchlist(next);
  }, []);
  return [watchlist, save] as const;
}

export type Theme = "dark" | "light";

export function initialTheme(): Theme {
  const saved = read(THEME_KEY);
  return saved === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme, persist = false): void {
  document.documentElement.dataset.theme = theme;
  if (persist) write(THEME_KEY, theme);
}
