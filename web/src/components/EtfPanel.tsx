import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useMemo, useRef, useState } from "react";
import { fetchChart, fetchMovers, fetchQuote, type Quote, type Range } from "../api";
import { extremes, liveState, withLastPrice } from "../chartMath";
import { Change, formatExact, formatPrice } from "../format";
import type { Instrument } from "../instruments";
import { InstrumentSearch } from "./InstrumentSearch";

const PriceChart = lazy(() => import("./PriceChart"));
const RANGES: Range[] = ["1D", "1W", "1M", "1Y", "ALL"];
const card = "rounded-2xl border border-line bg-surface shadow-sm";
const POLL_OPEN_MS = 15_000;
const POLL_CLOSED_MS = 120_000;

const clock = new Intl.DateTimeFormat("it", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

function useChart(symbol: string, range: Range) {
  return useQuery({
    queryKey: ["chart", symbol, range],
    queryFn: ({ signal }) => fetchChart(symbol, range, signal),
    staleTime: 60_000,
  });
}

function useQuote(symbol: string) {
  return useQuery({
    queryKey: ["quote", symbol],
    queryFn: ({ signal }) => fetchQuote(symbol, signal),
    // Si ferma da solo quando la scheda non e' visibile.
    refetchInterval: ({ state }) => (state.data?.is_open ? POLL_OPEN_MS : POLL_CLOSED_MS),
    staleTime: 5_000,
  });
}

function LivePrice({ quote }: { quote: Quote }) {
  const previous = useRef<number | null>(null);
  const price = quote.price;
  const flash = previous.current === null || price === previous.current || price === null
    ? "" : price > previous.current ? "animate-flash-up" : "animate-flash-down";
  previous.current = price;
  if (price === null) return null;
  // La chiave riavvia l'animazione a ogni nuovo prezzo.
  return (
    <p key={price} className={`text-lg leading-tight font-semibold tracking-tight tabular-nums ${flash}`}>
      {formatPrice(price, quote.currency)}
    </p>
  );
}

function LiveBadge({ quote }: { quote: Quote }) {
  const state = liveState(quote.is_open, quote.market_time, Date.now() / 1000);
  const time = quote.market_time ? clock.format(new Date(quote.market_time * 1000)) : null;
  const minutes = quote.market_time ? Math.round((Date.now() / 1000 - quote.market_time) / 60) : null;
  const label = state === "live" ? "LIVE" : state === "closed" ? "Chiuso" : minutes === null ? "Ritardato" : `Ritardato ${minutes} min`;
  return (
    <p className="flex items-center gap-1.5 text-[11px] text-muted tabular-nums">
      <span className="relative flex size-2">
        {state === "live" && <span className="absolute inset-0 animate-ping rounded-full bg-up opacity-60" />}
        <span className={`relative size-2 rounded-full ${state === "live" ? "bg-up" : state === "delayed" ? "bg-warn" : "bg-muted"}`} />
      </span>
      <span className={`font-semibold ${state === "live" ? "text-up" : ""}`}>{label}</span>
      {time && <span>· ultimo dato {time}</span>}
    </p>
  );
}

function EtfChart({ instrument, onSelect }: { instrument: Instrument; onSelect: (item: Instrument) => void }) {
  const [text, setText] = useState("");
  const [range, setRange] = useState<Range>("1D");
  const quote = useQuote(instrument.symbol).data;
  const series = useChart(instrument.symbol, range);
  const intraday = range === "1D" || range === "1W";

  const points = useMemo(() => {
    const base = series.data?.points ?? [];
    return intraday ? withLastPrice(base, quote?.market_time ?? null, quote?.price ?? null) : base;
  }, [series.data, intraday, quote?.market_time, quote?.price]);

  const reference = range === "1D"
    ? quote?.previous_close ?? series.data?.previous_close ?? null
    : points[0]?.value ?? null;
  const currency = quote?.currency ?? series.data?.currency ?? "";
  const range_ = extremes(points);

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
          <p className="mt-0.5 text-xs text-muted">{instrument.kind}{currency ? ` · ${currency}` : ""}</p>
        </div>
        <div className="shrink-0 text-right">
          {quote && <LivePrice quote={quote} />}
          {quote?.change_pct != null && <Change value={quote.change_pct} className="text-xs" />}
        </div>
      </div>
      {quote && <div className="mt-2"><LiveBadge quote={quote} /></div>}
      <div className="mt-1 h-36 lg:h-48">
        {series.isError && points.length === 0 ? (
          <p className="grid h-full place-items-center text-sm text-muted">{series.error.message}</p>
        ) : points.length > 0 ? (
          <Suspense fallback={<div className="skeleton h-full" />}>
            <PriceChart
              points={points}
              reference={reference}
              referenceLabel={range === "1D" ? "dalla chiusura precedente" : "dall'inizio del periodo"}
              currency={currency}
            />
          </Suspense>
        ) : series.isPending ? <div className="skeleton h-full" /> : (
          <p className="grid h-full place-items-center text-sm text-muted">Nessun dato per questo periodo.</p>
        )}
      </div>
      {range_ && (
        <p className="mt-1 flex justify-between text-[11px] text-muted tabular-nums">
          <span>Max <strong className="font-semibold text-up">{formatExact(range_.high.value, currency)}</strong></span>
          <span>Min <strong className="font-semibold text-down">{formatExact(range_.low.value, currency)}</strong></span>
        </p>
      )}
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
