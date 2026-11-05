import { useId, useMemo, useState, type KeyboardEvent, type Ref } from "react";
import { searchInstruments, type Instrument } from "../instruments";
import { SearchIcon } from "./icons";

interface InstrumentSearchProps {
  value: string;
  onChange: (value: string) => void;
  onSelect: (instrument: Instrument) => void;
  placeholder: string;
  label: string;
  hint?: string;
  inputRef?: Ref<HTMLInputElement>;
}

/** Campo con autocompletamento di ETF e indici, usato dalla ricerca globale e dal pannello. */
export function InstrumentSearch({ value, onChange, onSelect, placeholder, label, hint, inputRef }: InstrumentSearchProps) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const results = useMemo(() => searchInstruments(value), [value]);
  const expanded = open && results.length > 0;

  const choose = (instrument: Instrument) => {
    setOpen(false);
    onSelect(instrument);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      if (!expanded) onChange("");
      setOpen(false);
    } else if (expanded && event.key === "ArrowDown") {
      event.preventDefault();
      setActive((active + 1) % results.length);
    } else if (expanded && event.key === "ArrowUp") {
      event.preventDefault();
      setActive((active - 1 + results.length) % results.length);
    } else if (expanded && event.key === "Enter") {
      event.preventDefault();
      choose(results[Math.min(active, results.length - 1)]);
    }
  };

  return (
    <div className="relative min-w-0">
      <label className="flex items-center gap-2 rounded-full bg-raised px-3.5 py-2 text-sm transition-all duration-200 focus-within:bg-surface focus-within:ring-2 focus-within:ring-accent/40">
        <SearchIcon className="size-4 shrink-0 text-muted" />
        <span className="sr-only">{label}</span>
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={expanded ? `${listId}-${active}` : undefined}
          autoComplete="off"
          value={value}
          onChange={(event) => { onChange(event.target.value); setActive(0); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted"
        />
        {hint && <kbd className="hidden shrink-0 rounded-md border border-line bg-surface px-1.5 py-0.5 text-[11px] font-medium text-muted md:block">{hint}</kbd>}
      </label>
      {expanded && (
        <ul id={listId} role="listbox" aria-label="ETF e indici" className="absolute inset-x-0 top-full z-30 mt-1.5 overflow-hidden rounded-2xl border border-line bg-surface py-1 shadow-lg">
          {results.map((instrument, index) => (
            <li
              key={instrument.symbol}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              // mousedown: il click arriverebbe dopo il blur, a lista gia' chiusa.
              onMouseDown={(event) => { event.preventDefault(); choose(instrument); }}
              onMouseEnter={() => setActive(index)}
              className={`flex cursor-pointer items-baseline gap-2 px-3.5 py-2 text-sm ${index === active ? "bg-raised" : ""}`}
            >
              <span className="w-16 shrink-0 font-semibold tabular-nums">{instrument.ticker}</span>
              <span className="min-w-0 flex-1 truncate text-muted">{instrument.name}</span>
              <span className="shrink-0 text-[11px] text-muted">{instrument.kind}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
