export function formatNumber(value: number, decimals = 2): string {
  return new Intl.NumberFormat("it", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);
}

export function formatPrice(value: number, currency: string): string {
  if (!currency) return formatNumber(value);
  // GBp sono pence: il formato monetario standard non li gestisce.
  if (currency === "GBp") return `${formatNumber(value)} p`;
  return new Intl.NumberFormat("it", { style: "currency", currency }).format(value);
}

export function Change({ value, className = "" }: { value: number; className?: string }) {
  const color = value === 0 ? "text-muted" : value > 0 ? "text-up" : "text-down";
  return (
    <span className={`font-semibold tabular-nums ${color} ${className}`}>
      {value === 0 ? "=" : value > 0 ? "▲" : "▼"} {formatNumber(Math.abs(value))}%
      <span className="sr-only">{value > 0 ? " in rialzo" : value < 0 ? " in ribasso" : " invariato"}</span>
    </span>
  );
}
