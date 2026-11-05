export const FILTERS = [
  { id: "all", label: "Tutte", categories: [] },
  { id: "macro", label: "Macro", categories: ["macro", "microeconomics"] },
  { id: "fiscal", label: "Governo & Fisco", categories: ["fiscal_policy"] },
  { id: "central", label: "BCE/FED", categories: ["monetary_policy"] },
  { id: "eu", label: "Mercati UE", categories: ["stocks_eu"] },
  { id: "us", label: "USA", categories: ["stocks_us"] },
  { id: "bonds", label: "Bond", categories: ["bonds"] },
  { id: "commodities", label: "Materie prime", categories: ["commodities"] },
  { id: "crypto", label: "Crypto", categories: ["crypto"] },
] as const;

export type FilterId = (typeof FILTERS)[number]["id"];

export function FilterTabs({ value, onChange }: { value: FilterId; onChange: (id: FilterId) => void }) {
  return (
    <div className="no-scrollbar mx-auto flex max-w-7xl gap-1.5 overflow-x-auto px-4 pb-2.5">
      {FILTERS.map(({ id, label }) => (
        <button
          key={id}
          aria-pressed={value === id}
          onClick={() => onChange(id)}
          className="tactile shrink-0 rounded-full bg-raised px-3.5 py-1.5 text-[13px] font-medium whitespace-nowrap text-muted hover:text-text aria-pressed:bg-accent aria-pressed:font-semibold aria-pressed:text-on-accent"
        >
          {label}
        </button>
      ))}
    </div>
  );
}
