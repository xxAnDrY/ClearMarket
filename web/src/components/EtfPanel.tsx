import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";
import { fetchChart, fetchMovers, type Range } from "../api";
import { Change, formatPrice } from "../format";
import type { Instrument } from "../instruments";
import { InstrumentSearch } from "./InstrumentSearch";

const PriceChart = lazy(() => import("./PriceChart"));
const RANGES: Range[] = ["1D", "1W", "1M", "1Y", "ALL"];
const card = "rounded-2xl border border-line bg-surface shadow-sm";

function useChart(symbol: string, range: Range) {
  return useQuery({
    queryKey: ["chart", symbol, range],
    queryFn: ({ signal }) => fetchChart(symbol, range, signal),
    staleTime: 60_000,
    placeholderData: (previous) => (previous?.symbol === symbol ? previous : undefined),
  });
}

function EtfChart({ instrument, onSelect }: { instrument: Instrument; onSelect: (item: Instrument) => void }) {
  const [text, setText] = useState("");
  const [range, setRange] = useState<Range>("1M");
  // Quotazione e variazione giornaliera vengono sempre dal periodo 1D.
  const day = useChart(instrument.symbol, "1D");
  const series = useChart(instrument.symbol, range);
  const points = series.data?.points ?? [];

  return (
    <section id="etf" aria-label="ETF e indici" className={`${card} scroll-mt-32 p-4`}>
      <InstrumentSearch
        value={text}
        onChange={setText}
        onSelect={(item) => { setText(""); onSelect(item); }}
        label="Cerca ETF o indice"
        placeholder="CSPX, SWDA, MEUD, Stoxx…"
      />
      <div className="mt-3.5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">{instrument.ticker} · {instrument.name}</h2>
          <p className="mt-0.5 text-xs text-muted">{instrument.kind}{day.data?.currency ? ` · ${day.data.currency}` : ""}</p>
        </div>
        <div className="shrink-0 text-right">
          {day.data?.price != null && (
            <p className="text-lg leading-tight font-semibold tracking-tight tabular-nums">{formatPrice(day.data.price, day.data.currency)}</p>
          )}
          {day.data?.change_pct != null && <Change value={day.data.change_pct} className="text-xs" />}
        </div>
      </div>
      <div className="mt-2 h-32 lg:h-44">
        {series.isError && points.length === 0 ? (
          <p className="grid h-full place-items-center text-sm text-muted">{series.error.message}</p>
        ) : points.length > 0 ? (
          <Suspense fallback={<div className="skeleton h-full" />}>
            <PriceChart points={points} intraday={range === "1D" || range === "1W"} />
          </Suspense>
        ) : series.isPending ? <div className="skeleton h-full" /> : (
          <p className="grid h-full place-items-center text-sm text-muted">Nessun dato per questo periodo.</p>
        )}
      </div>
      <div role="group" aria-label="Periodo" className="mt-2 flex gap-1 rounded-full bg-raised p-1">
        {RANGES.map((item) => (
          <button
            key={item}
            aria-pressed={range === item}
            onClick={() => setRange(item)}
            className="tactile flex-1 rounded-full py-1 text-xs font-medium text-muted hover:text-text aria-pressed:bg-surface aria-pressed:font-semibold aria-pressed:text-accent aria-pressed:shadow-sm"
          >
            {item}
          </button>
        ))}
      </div>
    </section>
  );
}

function Movers() {
  const movers = useQuery({
    queryKey: ["movers"],
    queryFn: ({ signal }) => fetchMovers(signal),
    refetchInterval: 5 * 60_000,
  });
  if (movers.isError || movers.data?.length === 0) return null;
  return (
    <section aria-label="Market mover" className={card}>
      <h2 className="px-4 pt-3 text-sm font-semibold">Market mover</h2>
      <p className="px-4 text-xs text-muted">Maggiori variazioni di oggi tra i grandi titoli osservati</p>
      <ul className="mt-1.5 pb-1.5">
        {movers.isPending
          ? Array.from({ length: 3 }, (_, index) => <li key={index} className="px-4 py-2"><div className="skeleton h-4" /></li>)
          : movers.data.map((mover) => (
            <li key={mover.symbol} className="flex items-baseline justify-between gap-3 px-4 py-1.5 text-sm">
              <span className="min-w-0 truncate font-medium">{mover.label}</span>
              <span className="shrink-0 text-xs text-muted tabular-nums">{formatPrice(mover.price, mover.currency)}</span>
              <Change value={mover.change_pct} className="w-20 shrink-0 text-right text-xs" />
            </li>
          ))}
      </ul>
    </section>
  );
}

export function EtfPanel({ instrument, onSelect }: { instrument: Instrument; onSelect: (item: Instrument) => void }) {
  return (
    <div className="space-y-3">
      <EtfChart instrument={instrument} onSelect={onSelect} />
      <Movers />
    </div>
  );
}
