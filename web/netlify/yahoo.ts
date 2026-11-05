/** Accesso a Yahoo Finance dalle Netlify Functions: endpoint non ufficiali, dati ritardati. */
const BASE = "https://query1.finance.yahoo.com";
const USER_AGENT = "ClearMarketsBot/1.0";

export const SYMBOL = /^[A-Za-z0-9^=.-]{1,20}$/;

export interface YahooMeta {
  symbol: string;
  longName?: string;
  shortName?: string;
  currency?: string;
  regularMarketPrice?: number;
  regularMarketTime?: number;
  previousClose?: number;
  chartPreviousClose?: number;
  currentTradingPeriod?: { regular?: { start: number; end: number } };
}

export class UpstreamError extends Error {}

export async function yahooJson<T>(path: string, params: Record<string, string>): Promise<T> {
  const url = `${BASE}${path}?${new URLSearchParams(params)}`;
  const response = await fetch(url, {
    headers: { "User-Agent": USER_AGENT },
    signal: AbortSignal.timeout(8_000),
  });
  if (!response.ok) throw new UpstreamError(`yahoo ${response.status}`);
  return (await response.json()) as T;
}

export function changePct(meta: YahooMeta): number | null {
  const previous = meta.previousClose ?? meta.chartPreviousClose;
  if (!previous || meta.regularMarketPrice === undefined) return null;
  return Math.round(((meta.regularMarketPrice - previous) / previous) * 10_000) / 100;
}

/** La CDN di Netlify conserva la risposta: il traffico non si trasforma in chiamate a Yahoo. */
export function json(body: unknown, cdnSeconds: number, browserSeconds = 60): Response {
  return new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": browserSeconds ? `public, max-age=${browserSeconds}` : "no-cache",
      "Netlify-CDN-Cache-Control": `public, s-maxage=${cdnSeconds}, stale-while-revalidate=${cdnSeconds}`,
    },
  });
}

export function failure(status: number, error: string): Response {
  return new Response(JSON.stringify({ error }), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
