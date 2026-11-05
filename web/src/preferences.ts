export type Theme = "dark" | "light";

const THEME_KEY = "clearmarkets.theme";

// Lo storage puo' mancare (navigazione privata): la scelta resta solo per la visita.
export function initialTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: Theme, persist = false): void {
  document.documentElement.dataset.theme = theme;
  if (!persist) return;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* nessuna persistenza disponibile */
  }
}
