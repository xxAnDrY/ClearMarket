import { useQuery } from "@tanstack/react-query";
import { fetchMarkets, type MarketQuote } from "../api";
import { Change, formatNumber } from "../format";
import { dateTime, relativeTime } from "../time";

function formatValue({ value, decimals, unit }: MarketQuote): string {
  const number = formatNumber(value, decimals);
  if (unit === "$") return `$${number}`;
  return unit ? `${number} ${unit}` : number;
}

function Items({ quotes, updated }: { quotes: MarketQuote[]; updated: string }) {
  return (
    <>
      {quotes.map((quote) => (
        <span key={quote.symbol} title={`Dato del ${dateTime(quote.as_of)}`} className="flex shrink-0 items-baseline gap-1.5 pr-6">
          <span className="font-medium text-muted">{quote.label}</span>
          <span className="font-semibold tabular-nums">{formatValue(quote)}</span>
          {quote.change_pct !== null && <Change value={quote.change_pct} />}
        </span>
      ))}
      <span className="shrink-0 pr-6 text-[11px] text-muted">Aggiornato {relativeTime(updated)} · dati ritardati</span>
    </>
  );
}

/** Striscia scorrevole. Non mostra mai valori inventati: senza dati non occupa spazio. */
export function MarketBar() {
  const markets = useQuery({
    queryKey: ["markets"],
    queryFn: ({ signal }) => fetchMarkets(signal),
    refetchInterval: 5 * 60_000,
  }).data;
  if (!markets || markets.quotes.length === 0) return null;
  return (
    <section aria-label="Mercati" className="no-scrollbar relative min-w-0 overflow-hidden text-xs motion-reduce:overflow-x-auto">
      <div className="flex w-max animate-marquee hover:[animation-play-state:paused] motion-reduce:animate-none">
        <div className="flex"><Items quotes={markets.quotes} updated={markets.generated_at} /></div>
        {/* Copia per chiudere il ciclo senza stacchi. */}
        <div aria-hidden="true" className="flex motion-reduce:hidden"><Items quotes={markets.quotes} updated={markets.generated_at} /></div>
      </div>
    </section>
  );
}
