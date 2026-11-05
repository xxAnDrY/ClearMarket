export type Sentiment = "positive" | "neutral" | "negative";

export interface Article {
  id: string;
  title: string;
  summary: string;
  source: { slug: string; name: string };
  source_url: string;
  translated: boolean;
  published_at: string;
  category: string;
  related_tickers: string[];
  sentiment: { label: Sentiment; score: number };
}

export interface EconomicEvent {
  id: string;
  title: string;
  country: string;
  starts_at: string;
  impact: "low" | "medium" | "high" | "holiday";
  forecast: string | null;
  previous: string | null;
  actual: string | null;
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

interface Stamped {
  generated_at: string;
}

export type FeedFile = Stamped & { articles: Article[] };
export type MarketsFile = Stamped & { quotes: MarketQuote[] };
export type CalendarFile = Stamped & { events: EconomicEvent[] };

export type FeedQuery =
  | { kind: "all"; categories: string[]; search: string }
  | { kind: "watchlist"; tickers: string[]; categories: string[] };

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

async function loadData<T extends Stamped>(file: string, signal?: AbortSignal): Promise<T> {
  try {
    const response = await fetch(`/live/${file}`, { signal });
    if (response.ok) return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
  }
  throw new ApiError("Dati non disponibili. Riprova tra poco.");
}

export const fetchFeed = (signal?: AbortSignal) => loadData<FeedFile>("feed.json", signal);
export const fetchMarkets = (signal?: AbortSignal) => loadData<MarketsFile>("markets.json", signal);
export const fetchCalendar = (signal?: AbortSignal) => loadData<CalendarFile>("calendar.json", signal);

export function filterArticles(articles: Article[], query: FeedQuery): Article[] {
  if (query.kind === "watchlist") {
    return articles.filter((article) =>
      query.categories.includes(article.category)
      || article.related_tickers.some((ticker) => query.tickers.includes(ticker)));
  }
  const term = query.search.toLowerCase();
  return articles.filter((article) =>
    (query.categories.length === 0 || query.categories.includes(article.category))
    && (!term
      || article.title.toLowerCase().includes(term)
      || article.summary.toLowerCase().includes(term)
      || article.related_tickers.some((ticker) => ticker.toLowerCase() === term)));
}

export function eventsOn(events: EconomicEvent[], day: Date): EconomicEvent[] {
  return events.filter((event) => new Date(event.starts_at).toDateString() === day.toDateString());
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
