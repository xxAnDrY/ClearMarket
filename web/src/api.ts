export type Sentiment = "positive" | "neutral" | "negative";

export interface Article {
  id: string;
  title: string;
  summary: string;
  source: { slug: string; name: string };
  source_url: string;
  language: string;
  published_at: string;
  category: string;
  related_tickers: string[];
  sentiment: { label: Sentiment; score: number };
}

export interface MarketQuote {
  symbol: string;
  label: string;
  value: number;
  change_pct: number | null;
  unit: string;
  decimals: number;
  as_of: string;
}

export type Range = "1D" | "1W" | "1M" | "1Y" | "ALL";

export interface Chart {
  symbol: string;
  name: string;
  currency: string;
  previous_close: number | null;
  points: { time: number; value: number }[];
}

export interface Quote {
  symbol: string;
  currency: string;
  price: number | null;
  previous_close: number | null;
  change_pct: number | null;
  market_time: number | null;
  is_open: boolean;
}

export interface Mover {
  symbol: string;
  label: string;
  price: number;
  currency: string;
  change_pct: number;
}

export interface NewsQuery {
  categories: string[];
  search: string;
}

interface Stamped {
  generated_at: string;
}

export type FeedFile = Stamped & { articles: Article[] };
export type MarketsFile = Stamped & { quotes: MarketQuote[] };

export const CATEGORIES: Record<string, string> = {
  macro: "Macroeconomia",
  monetary_policy: "Politica monetaria",
  fiscal_policy: "Politica economica",
  microeconomics: "Microeconomia",
  stocks_eu: "Azioni UE",
  stocks_us: "Azioni USA",
  bonds: "Obbligazioni",
  commodities: "Materie prime",
  etf: "ETF",
  crypto: "Crypto",
};

export class ApiError extends Error {}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  try {
    const response = await fetch(url, { signal });
    if (response.ok) return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
  }
  throw new ApiError("Dati non disponibili. Riprova tra poco.");
}

export const fetchFeed = (signal?: AbortSignal) => getJson<FeedFile>("/live/feed.json", signal);
export const fetchMarkets = (signal?: AbortSignal) => getJson<MarketsFile>("/live/markets.json", signal);

export const fetchChart = (symbol: string, range: Range, signal?: AbortSignal) =>
  getJson<Chart>(`/api/chart?${new URLSearchParams({ symbol, range })}`, signal);

export const fetchQuote = (symbol: string, signal?: AbortSignal) =>
  getJson<Quote>(`/api/quote?${new URLSearchParams({ symbol })}`, signal);

export const fetchMovers = async (signal?: AbortSignal) =>
  (await getJson<{ movers: Mover[] }>("/api/movers", signal)).movers;

export function filterArticles(articles: Article[], { categories, search }: NewsQuery): Article[] {
  const term = search.toLowerCase();
  return articles.filter((article) =>
    (categories.length === 0 || categories.includes(article.category))
    && (!term
      || article.title.toLowerCase().includes(term)
      || article.summary.toLowerCase().includes(term)
      || article.related_tickers.some((ticker) => ticker.toLowerCase() === term)));
}

/** Lun-ven, 08:30-22:30 ora di Roma, a prescindere dal fuso del visitatore. */
export function isMarketOpen(now = new Date()): boolean {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Rome", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(now);
  const value = (type: string) => parts.find((part) => part.type === type)!.value;
  const minutes = Number(value("hour")) * 60 + Number(value("minute"));
  return !["Sat", "Sun"].includes(value("weekday")) && minutes >= 8 * 60 + 30 && minutes < 22 * 60 + 30;
}

/** Solo http e https: il link arriva da feed di terzi. */
export function safeUrl(url: string): string | undefined {
  try {
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:" ? url : undefined;
  } catch {
    return undefined;
  }
}
