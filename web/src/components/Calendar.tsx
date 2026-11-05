import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchEvents, localDate, type EconomicEvent } from "../api";
import { clockTime, longDate } from "../time";

const IMPACT: Record<EconomicEvent["impact"], { label: string; dot: string }> = {
  high: { label: "Impatto alto", dot: "bg-down" },
  medium: { label: "Impatto medio", dot: "bg-accent" },
  low: { label: "Impatto basso", dot: "bg-muted" },
  holiday: { label: "Festività", dot: "bg-muted" },
};

function useEvents(day: Date) {
  return useQuery({
    queryKey: ["calendar", localDate(day)],
    queryFn: ({ signal }) => fetchEvents(day, signal),
    staleTime: 5 * 60_000,
  });
}

function EventRow({ event }: { event: EconomicEvent }) {
  const impact = IMPACT[event.impact];
  const figures = [
    event.actual && `Eff. ${event.actual}`,
    event.forecast && `Prev. ${event.forecast}`,
    event.previous && `Prec. ${event.previous}`,
  ].filter(Boolean).join("   ");
  return (
    <li className="flex gap-3 border-b border-line/60 px-4 py-3 text-sm last:border-b-0">
      <time dateTime={event.starts_at} className="w-11 shrink-0 font-semibold tabular-nums">{clockTime(event.starts_at)}</time>
      <span title={impact.label} className={`mt-1.5 size-2 shrink-0 rounded-full ${impact.dot}`}>
        <span className="sr-only">{impact.label}</span>
      </span>
      <div className="min-w-0">
        <p className="font-semibold"><span className="text-muted">{event.country}</span> {event.title}</p>
        {figures && <p className="mt-0.5 text-xs whitespace-pre-wrap text-muted tabular-nums">{figures}</p>}
      </div>
    </li>
  );
}

export function CalendarPage() {
  const [day, setDay] = useState(() => new Date());
  const events = useEvents(day);
  const shift = (days: number) => setDay(new Date(day.getFullYear(), day.getMonth(), day.getDate() + days));

  return (
    <section aria-label="Calendario economico" className="overflow-hidden rounded-2xl border border-line bg-surface shadow-sm">
      <div className="flex items-center justify-between border-b border-line px-2 py-1.5">
        <button aria-label="Giorno precedente" onClick={() => shift(-1)} className="tactile rounded-full px-3 py-1 text-lg hover:bg-raised">‹</button>
        <h1 className="text-sm font-semibold first-letter:uppercase">{longDate(day)}</h1>
        <button aria-label="Giorno successivo" onClick={() => shift(1)} className="tactile rounded-full px-3 py-1 text-lg hover:bg-raised">›</button>
      </div>
      {events.isPending && <p className="px-4 py-16 text-center text-muted">Caricamento…</p>}
      {events.isError && <p className="px-4 py-16 text-center text-muted">{events.error.message}</p>}
      {events.data?.length === 0 && <p className="px-4 py-16 text-center text-muted">Nessun evento per questo giorno.</p>}
      {!!events.data?.length && <ul>{events.data.map((event) => <EventRow key={event.id} event={event} />)}</ul>}
      <p className="px-4 py-3 text-xs text-muted">I nomi degli eventi sono nella lingua della fonte.</p>
    </section>
  );
}

/** Colonna laterale su desktop: solo gli eventi di oggi che muovono i mercati. */
export function TodayPanel() {
  const [today] = useState(() => new Date());
  const events = useEvents(today).data?.filter(({ impact }) => impact === "high" || impact === "medium");
  return (
    <aside aria-label="Agenda di oggi" className="overflow-hidden rounded-2xl border border-line bg-surface shadow-sm">
      <div className="flex items-baseline justify-between border-b border-line px-4 py-2.5">
        <h2 className="text-sm font-bold">Agenda di oggi</h2>
        <a href="#/calendario" className="text-xs font-semibold text-accent">Tutti</a>
      </div>
      {events?.length === 0 && <p className="px-4 py-6 text-sm text-muted">Nessun evento rilevante.</p>}
      {!!events?.length && <ul className="no-scrollbar max-h-[calc(100vh-12rem)] overflow-y-auto">{events.map((event) => <EventRow key={event.id} event={event} />)}</ul>}
    </aside>
  );
}
