/** Forma compatta per le card: "12m fa", "3h fa", "2g fa". */
export function relativeTime(iso: string, now = Date.now()): string {
  const minutes = Math.round((now - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "adesso";
  if (minutes < 60) return `${minutes}m fa`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h fa`;
  return `${Math.round(hours / 24)}g fa`;
}

export const clockTime = (iso: string) =>
  new Intl.DateTimeFormat("it", { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));

export const longDate = (date: Date) =>
  new Intl.DateTimeFormat("it", { weekday: "long", day: "numeric", month: "long" }).format(date);

export const dateTime = (iso: string) =>
  new Intl.DateTimeFormat("it", { dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
