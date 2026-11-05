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

export interface FeedPage {
  data: Article[];
  page_info: { next_cursor: string | null; has_more: boolean; limit: number };
}

export interface Category {
  slug: string;
  label: string;
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

export interface Markets {
  market_open: boolean;
  quotes: MarketQuote[];
}

export type FeedQuery =
  | { kind: "all"; categories: string[]; search: string }
  | { kind: "watchlist"; tickers: string[]; categories: string[] };

export class ApiError extends Error {}

async function get<T>(path: string, params: URLSearchParams, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${path}?${params}`, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Connessione non disponibile. Riprova.");
  }
  if (response.status === 429) throw new ApiError("Troppe richieste. Riprova tra un minuto.");
  if (!response.ok) throw new ApiError("Il servizio non risponde. Riprova tra poco.");
  return response.json() as Promise<T>;
}

export function feedParams(query: FeedQuery, cursor: string | null): URLSearchParams {
  const params = new URLSearchParams({ limit: "20" });
  query.categories.forEach((category) => params.append("category", category));
  if (query.kind === "all") {
    if (query.search) params.set("q", query.search);
  } else {
    params.set("match", "any");
    query.tickers.forEach((ticker) => params.append("ticker", ticker));
  }
  if (cursor) params.set("cursor", cursor);
  return params;
}

export const fetchFeed = (query: FeedQuery, cursor: string | null, signal?: AbortSignal) =>
  get<FeedPage>("/api/v1/feed", feedParams(query, cursor), signal);

export const fetchCategories = (signal?: AbortSignal) =>
  get<Category[]>("/api/v1/categories", new URLSearchParams(), signal);

export const fetchMarkets = (signal?: AbortSignal) =>
  get<Markets>("/api/v1/markets", new URLSearchParams(), signal);

export function localDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export async function fetchEvents(day: Date, signal?: AbortSignal): Promise<EconomicEvent[]> {
  const params = new URLSearchParams({
    date: localDate(day),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  });
  const body = await get<{ data: EconomicEvent[] }>("/api/v1/calendar", params, signal);
  return body.data;
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
