import { useQuery } from "@tanstack/react-query";
import { fetchMarkets, type MarketQuote } from "../api";
import { dateTime } from "../time";

export function useMarkets() {
  return useQuery({
    queryKey: ["markets"],
    queryFn: ({ signal }) => fetchMarkets(signal),
    refetchInterval: 60_000,
  });
}

function formatValue({ value, decimals, unit }: MarketQuote): string {
  const number = new Intl.NumberFormat("it", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
  if (unit === "$") return `$${number}`;
  return unit ? `${number} ${unit}` : number;
}

function Change({ value }: { value: number }) {
  const flat = value === 0;
  const color = flat ? "text-muted" : value > 0 ? "text-up" : "text-down";
  const text = new Intl.NumberFormat("it", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Math.abs(value));
  return (
    <span className={`font-semibold tabular-nums ${color}`}>
      {flat ? "=" : value > 0 ? "▲" : "▼"} {text}%
      <span className="sr-only">{value > 0 ? " in rialzo" : value < 0 ? " in ribasso" : " invariato"}</span>
    </span>
  );
}

/** Non mostra mai valori inventati: senza dati la barra non occupa spazio. */
export function MarketBar() {
  const quotes = useMarkets().data?.quotes ?? [];
  if (quotes.length === 0) return null;
  return (
    <section aria-label="Mercati" className="border-b border-line bg-surface">
      <div className="no-scrollbar relative mx-auto flex max-w-7xl items-center gap-6 overflow-x-auto px-4 py-1.5 text-xs">
        {quotes.map((quote) => (
          <div key={quote.symbol} title={`Dato del ${dateTime(quote.as_of)}`} className="flex shrink-0 items-baseline gap-1.5">
            <span className="font-medium text-muted">{quote.label}</span>
            <span className="font-semibold tabular-nums">{formatValue(quote)}</span>
            {quote.change_pct !== null && <Change value={quote.change_pct} />}
          </div>
        ))}
        <span className="ml-auto shrink-0 pl-4 text-[11px] text-muted">Dati ritardati</span>
      </div>
    </section>
  );
}
