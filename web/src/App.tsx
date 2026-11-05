import { useEffect, useMemo, useState } from "react";
import { EtfPanel } from "./components/EtfPanel";
import { FilterTabs, FILTERS, type FilterId } from "./components/FilterTabs";
import { Navbar } from "./components/Navbar";
import { NewsCardGrid } from "./components/NewsCardGrid";
import { DEFAULT_INSTRUMENT, type Instrument } from "./instruments";

const MIN_SEARCH = 2;

function useDebounced(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function App() {
  const [filter, setFilter] = useState<FilterId>("all");
  const [search, setSearch] = useState("");
  const [instrument, setInstrument] = useState(DEFAULT_INSTRUMENT);
  const debounced = useDebounced(search.trim(), 250);
  const activeSearch = debounced.length >= MIN_SEARCH ? debounced : "";
  const query = useMemo(
    () => ({ categories: [...FILTERS.find(({ id }) => id === filter)!.categories], search: activeSearch }),
    [filter, activeSearch],
  );

  // Dalla ricerca globale il grafico puo' essere fuori schermo, soprattutto su telefono.
  const openInstrument = (item: Instrument) => {
    setInstrument(item);
    setSearch("");
    document.getElementById("etf")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <>
      {/* Su telefono resta fisso solo il filtro: lo schermo serve alle notizie. */}
      <header className="relative z-20 bg-surface/80 backdrop-blur-md lg:sticky lg:top-0">
        <Navbar search={search} onSearch={setSearch} onInstrument={openInstrument} />
      </header>
      <div className="sticky top-0 z-10 border-b border-line/60 bg-surface/80 pt-1 backdrop-blur-md lg:top-14 lg:pt-0">
        <FilterTabs value={filter} onChange={setFilter} />
      </div>

      <div className="mx-auto grid max-w-7xl gap-4 px-3 pt-4 sm:px-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="lg:order-last">
          <div className="lg:sticky lg:top-28"><EtfPanel instrument={instrument} onSelect={setInstrument} /></div>
        </div>
        <main className="min-w-0">
          {activeSearch && (
            <p className="mb-3 flex items-center gap-2 px-1 text-sm text-muted">
              Notizie per <strong className="text-text">{activeSearch}</strong>
              <button onClick={() => setSearch("")} className="tactile font-semibold text-accent">Annulla</button>
            </p>
          )}
          <NewsCardGrid query={query} onTicker={setSearch} />
        </main>
      </div>

      <footer className="mx-auto max-w-7xl px-4 pt-4 pb-8 text-xs leading-relaxed text-muted">
        Notizie di terze parti, con link alla fonte originale. Quotazioni ritardate; traduzioni e sentiment automatici possono contenere errori. Non è consulenza finanziaria.
      </footer>
    </>
  );
}
