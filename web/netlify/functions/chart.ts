import { changePct, failure, json, SYMBOL, yahooJson, type YahooMeta } from "../yahoo";

const RANGES: Record<string, { range: string; interval: string; cdnSeconds: number }> = {
  "1D": { range: "1d", interval: "5m", cdnSeconds: 300 },
  "1W": { range: "5d", interval: "30m", cdnSeconds: 900 },
  "1M": { range: "1mo", interval: "1d", cdnSeconds: 3_600 },
  "1Y": { range: "1y", interval: "1d", cdnSeconds: 3_600 },
  ALL: { range: "max", interval: "1mo", cdnSeconds: 21_600 },
};

interface ChartResponse {
  chart: {
    result: Array<{
      meta: YahooMeta;
      timestamp?: number[];
      indicators: { quote: Array<{ close?: Array<number | null> }> };
    }> | null;
  };
}

export default async (request: Request): Promise<Response> => {
  const params = new URL(request.url).searchParams;
  const symbol = params.get("symbol") ?? "";
  const selected = RANGES[params.get("range") ?? "1D"];
  // Solo simboli e periodi validi: la funzione non e' un proxy generico.
  if (!SYMBOL.test(symbol) || !selected) return failure(400, "invalid request");

  try {
    const data = await yahooJson<ChartResponse>(`/v8/finance/chart/${encodeURIComponent(symbol)}`, {
      range: selected.range,
      interval: selected.interval,
    });
    const result = data.chart.result?.[0];
    if (!result) return failure(404, "symbol not found");

    const closes = result.indicators.quote[0]?.close ?? [];
    const points = (result.timestamp ?? []).flatMap((time, index) => {
      const value = closes[index];
      return typeof value === "number" ? [{ time, value }] : [];
    });
    const { meta } = result;
    return json({
      symbol: meta.symbol,
      name: meta.longName ?? meta.shortName ?? meta.symbol,
      currency: meta.currency ?? "",
      price: meta.regularMarketPrice ?? null,
      change_pct: selected.range === "1d" ? changePct(meta) : null,
      as_of: meta.regularMarketTime ? new Date(meta.regularMarketTime * 1000).toISOString() : null,
      points,
    }, selected.cdnSeconds);
  } catch {
    return failure(502, "market data unavailable");
  }
};

export const config = { path: "/api/chart" };
