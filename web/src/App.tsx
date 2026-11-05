import { useEffect, useState } from "react";
import { CalendarPage, TodayPanel } from "./components/Calendar";
import { FilterTabs, FILTERS, type FilterId } from "./components/FilterTabs";
import { CalendarIcon, NewsIcon, StarIcon } from "./components/icons";
import { MarketBar } from "./components/MarketBar";
import { Navbar, ROUTES } from "./components/Navbar";
import { NewsCardGrid } from "./components/NewsCardGrid";
import { WatchlistPage } from "./components/Watchlist";

const MIN_SEARCH = 2;
const ROUTE_ICONS = [NewsIcon, StarIcon, CalendarIcon];

function useRoute() {
  const current = () => (ROUTES.some(({ hash }) => hash === location.hash) ? location.hash : "#/");
  const [route, setRoute] = useState(current);
  useEffect(() => {
    const update = () => { setRoute(current()); scrollTo(0, 0); };
    addEventListener("hashchange", update);
    return () => removeEventListener("hashchange", update);
  }, []);
  return route;
}

function useDebounced(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function App() {
  const route = useRoute();
  const [filter, setFilter] = useState<FilterId>("all");
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search.trim(), 250);
  const activeSearch = debounced.length >= MIN_SEARCH ? debounced : "";
  const categories = [...FILTERS.find(({ id }) => id === filter)!.categories];

  const onSearch = (value: string) => {
    setSearch(value);
    if (value && route !== "#/") location.hash = "#/";
  };

  return (
    <>
      <MarketBar />
      <header className="sticky top-0 z-20 border-b border-line/60 bg-surface/80 backdrop-blur-md">
        <Navbar route={route} search={search} onSearch={onSearch} />
        {route === "#/" && <FilterTabs value={filter} onChange={setFilter} />}
      </header>

      <div className={`mx-auto grid max-w-7xl gap-4 px-3 pt-4 sm:px-4 ${route === "#/calendario" ? "" : "xl:grid-cols-[minmax(0,1fr)_320px]"}`}>
        <main className="min-w-0">
          {route === "#/" && (
            <>
              {activeSearch && (
                <p className="mb-3 flex items-center gap-2 px-1 text-sm text-muted">
                  Risultati per <strong className="text-text">{activeSearch}</strong>
                  <button onClick={() => setSearch("")} className="tactile font-semibold text-accent">Annulla</button>
                </p>
              )}
              <NewsCardGrid query={{ kind: "all", categories, search: activeSearch }} onTicker={onSearch} />
            </>
          )}
          {route === "#/watchlist" && <WatchlistPage onTicker={onSearch} />}
          {route === "#/calendario" && <CalendarPage />}
        </main>
        {route !== "#/calendario" && (
          <div className="hidden xl:block"><div className="sticky top-32"><TodayPanel /></div></div>
        )}
      </div>

      <footer className="mx-auto max-w-7xl px-4 pt-4 pb-24 text-xs leading-relaxed text-muted md:pb-8">
        Notizie di terze parti, con link alla fonte originale. Traduzioni e sentiment sono automatici e possono contenere errori. Non è consulenza finanziaria.
      </footer>

      <nav aria-label="Sezioni" className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-3 border-t border-line/60 bg-surface/80 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden">
        {ROUTES.map(({ hash, label }, index) => {
          const Icon = ROUTE_ICONS[index];
          return (
            <a
              key={hash}
              href={hash}
              aria-current={route === hash ? "page" : undefined}
              className="tactile flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-muted aria-[current=page]:text-accent"
            >
              <Icon className="size-5" />
              {label}
            </a>
          );
        })}
      </nav>
    </>
  );
}
