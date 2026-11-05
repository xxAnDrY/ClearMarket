import { changePct, failure, json, yahooJson, type YahooMeta } from "../yahoo";

/** Paniere osservato: grandi titoli italiani, europei e americani. Non e' l'intero mercato. */
const BASKET: Record<string, string> = {
  "ENI.MI": "Eni", "ENEL.MI": "Enel", "ISP.MI": "Intesa Sanpaolo", "UCG.MI": "UniCredit",
  "RACE.MI": "Ferrari", "STLAM.MI": "Stellantis", "ASML.AS": "ASML", "SAP.DE": "SAP",
  "MC.PA": "LVMH", "NVDA": "Nvidia", "AAPL": "Apple", "MSFT": "Microsoft", "AMZN": "Amazon",
  "GOOGL": "Alphabet", "META": "Meta", "TSLA": "Tesla",
};
const TOP = 3;

interface SparkResponse {
  spark: { result: Array<{ symbol: string; response: Array<{ meta: YahooMeta }> }> | null };
}

export default async (): Promise<Response> => {
  try {
    const data = await yahooJson<SparkResponse>("/v7/finance/spark", {
      symbols: Object.keys(BASKET).join(","),
      range: "1d",
      interval: "1d",
    });
    const movers = (data.spark.result ?? []).flatMap(({ symbol, response }) => {
      const meta = response[0]?.meta;
      const change = meta ? changePct(meta) : null;
      if (!meta || change === null) return [];
      return [{ symbol, label: BASKET[symbol] ?? symbol, price: meta.regularMarketPrice,
                currency: meta.currency ?? "", change_pct: change }];
    }).sort((first, second) => Math.abs(second.change_pct) - Math.abs(first.change_pct));
    return json({ movers: movers.slice(0, TOP) }, 300);
  } catch {
    return failure(502, "market data unavailable");
  }
};

export const config = { path: "/api/movers" };
