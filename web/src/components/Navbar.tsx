import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { isMarketOpen } from "../api";
import { applyTheme, initialTheme, type Theme } from "../preferences";
import { MoonIcon, RefreshIcon, SearchIcon, SunIcon } from "./icons";

export const ROUTES = [
  { hash: "#/", label: "Notizie" },
  { hash: "#/watchlist", label: "Watchlist" },
  { hash: "#/calendario", label: "Calendario" },
];

const iconButton = "tactile grid size-9 shrink-0 place-items-center rounded-full text-muted hover:bg-raised hover:text-text";
const isMac = /Mac|iPhone|iPad/.test(navigator.platform);

function MarketStatus() {
  const open = isMarketOpen();
  return (
    <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-muted">
      <span className="relative flex size-2">
        {open && <span className="absolute inset-0 animate-ping rounded-full bg-up opacity-60" />}
        <span className={`relative size-2 rounded-full ${open ? "bg-up" : "bg-warn"}`} />
      </span>
      <span className="hidden lg:inline">{open ? "Mercati aperti" : "Mercati chiusi"}</span>
      <span className="sr-only lg:hidden">{open ? "Mercati aperti" : "Mercati chiusi"}</span>
    </span>
  );
}

function RefreshButton() {
  const client = useQueryClient();
  const fetching = useIsFetching() > 0;
  return (
    <button aria-label="Aggiorna" onClick={() => void client.invalidateQueries()} className={iconButton}>
      <RefreshIcon className={`size-4 ${fetching ? "animate-spin" : ""}`} />
    </button>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      aria-label={next === "light" ? "Passa al tema chiaro" : "Passa al tema scuro"}
      onClick={() => { applyTheme(next, true); setTheme(next); }}
      className={iconButton}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

interface NavbarProps {
  route: string;
  search: string;
  onSearch: (value: string) => void;
}

export function Navbar({ route, search, onSearch }: NavbarProps) {
  const input = useRef<HTMLInputElement>(null);
  const [mobileSearch, setMobileSearch] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setMobileSearch(true);
        // Su mobile il campo diventa visibile solo dopo il render.
        setTimeout(() => input.current?.focus());
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5 md:flex-nowrap">
      <a href="#/" className="tactile shrink-0 text-[17px] font-bold tracking-tight">
        Clear<span className="text-accent">Market</span>
      </a>

      <nav aria-label="Sezioni" className="hidden items-center gap-0.5 md:flex">
        {ROUTES.map(({ hash, label }) => (
          <a
            key={hash}
            href={hash}
            aria-current={route === hash ? "page" : undefined}
            className="tactile rounded-full px-3 py-1.5 text-sm font-medium text-muted hover:text-text aria-[current=page]:bg-accent/10 aria-[current=page]:font-semibold aria-[current=page]:text-accent"
          >
            {label}
          </a>
        ))}
      </nav>

      <label className={`${mobileSearch ? "flex" : "hidden"} order-last w-full items-center gap-2 rounded-full bg-raised px-3.5 py-2 text-sm transition-all duration-200 focus-within:bg-surface focus-within:ring-2 focus-within:ring-accent/40 md:order-none md:mx-auto md:flex md:max-w-sm`}>
        <SearchIcon className="size-4 shrink-0 text-muted" />
        <span className="sr-only">Cerca notizie o ticker</span>
        <input
          ref={input}
          type="search"
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Escape") { onSearch(""); event.currentTarget.blur(); } }}
          placeholder="Cerca notizie o ticker"
          className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted [&::-webkit-search-cancel-button]:hidden"
        />
        <kbd className="hidden shrink-0 rounded-md border border-line bg-surface px-1.5 py-0.5 text-[11px] font-medium text-muted md:block">
          {isMac ? "⌘K" : "Ctrl K"}
        </kbd>
      </label>

      <div className="ml-auto flex items-center gap-1 md:ml-0">
        <MarketStatus />
        <button
          aria-label="Cerca"
          aria-expanded={mobileSearch}
          onClick={() => { setMobileSearch(!mobileSearch); setTimeout(() => input.current?.focus()); }}
          className={`${iconButton} md:hidden`}
        >
          <SearchIcon />
        </button>
        <RefreshButton />
        <ThemeToggle />
      </div>
    </div>
  );
}
