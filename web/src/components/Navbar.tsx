import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { isMarketOpen } from "../api";
import type { Instrument } from "../instruments";
import { applyTheme, initialTheme, type Theme } from "../preferences";
import { MoonIcon, RefreshIcon, SunIcon } from "./icons";
import { InstrumentSearch } from "./InstrumentSearch";
import { MarketBar } from "./MarketBar";

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
      <span className="hidden xl:inline">{open ? "Mercati aperti" : "Mercati chiusi"}</span>
      <span className="sr-only xl:hidden">{open ? "Mercati aperti" : "Mercati chiusi"}</span>
    </span>
  );
}

function RefreshButton() {
  const client = useQueryClient();
  // Il polling della quotazione non deve far girare l'icona ogni 15 secondi.
  const fetching = useIsFetching({ predicate: ({ queryKey }) => queryKey[0] !== "quote" }) > 0;
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
  search: string;
  onSearch: (value: string) => void;
  onInstrument: (instrument: Instrument) => void;
}

export function Navbar({ search, onSearch, onInstrument }: NavbarProps) {
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        input.current?.focus();
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="mx-auto grid max-w-7xl grid-cols-[auto_1fr_auto] items-center gap-x-4 gap-y-2 px-4 py-2.5 lg:grid-cols-[auto_minmax(0,1fr)_18rem_auto]">
      <a href="/" className="tactile text-[17px] font-semibold tracking-[-0.03em]">
        Clear<span className="text-accent">Markets</span>
      </a>
      <div className="col-span-3 row-start-3 min-w-0 lg:col-span-1 lg:row-start-auto"><MarketBar /></div>
      <div className="col-span-3 row-start-2 min-w-0 lg:col-span-1 lg:row-start-auto">
        <InstrumentSearch
          inputRef={input}
          value={search}
          onChange={onSearch}
          onSelect={onInstrument}
          label="Cerca notizie, ETF o indici"
          placeholder="Cerca notizie, ETF, indici"
          hint={isMac ? "⌘K" : "Ctrl K"}
        />
      </div>
      <div className="col-start-3 row-start-1 flex items-center gap-1 lg:col-start-4">
        <MarketStatus />
        <RefreshButton />
        <ThemeToggle />
      </div>
    </div>
  );
}
