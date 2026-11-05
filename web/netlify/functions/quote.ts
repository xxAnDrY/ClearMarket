import { changePct, failure, json, SYMBOL, yahooJson, type YahooMeta } from "../yahoo";

interface ChartResponse {
  chart: { result: Array<{ meta: YahooMeta }> | null };
}

export function toQuote(meta: YahooMeta, nowSeconds: number) {
  const session = meta.currentTradingPeriod?.regular;
  return {
    symbol: meta.symbol,
    currency: meta.currency ?? "",
    price: meta.regularMarketPrice ?? null,
    previous_close: meta.previousClose ?? meta.chartPreviousClose ?? null,
    change_pct: changePct(meta),
    market_time: meta.regularMarketTime ?? null,
    is_open: !!session && nowSeconds >= session.start && nowSeconds < session.end,
  };
}

/** Ultima quotazione di un simbolo: la CDN la condivide tra i visitatori per 10 secondi. */
export default async (request: Request): Promise<Response> => {
  const symbol = new URL(request.url).searchParams.get("symbol") ?? "";
  if (!SYMBOL.test(symbol)) return failure(400, "invalid request");
  try {
    const data = await yahooJson<ChartResponse>(`/v8/finance/chart/${encodeURIComponent(symbol)}`, {
      range: "1d",
      interval: "1d",
    });
    const meta = data.chart.result?.[0]?.meta;
    if (!meta) return failure(404, "symbol not found");
    return json(toQuote(meta, Date.now() / 1000), 10, 0);
  } catch {
    return failure(502, "market data unavailable");
  }
};

export const config = { path: "/api/quote" };
