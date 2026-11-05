export interface Instrument {
  symbol: string;   // simbolo Yahoo
  ticker: string;   // come lo cerca un investitore
  name: string;
  kind: "ETF" | "Indice";
  aliases?: string;
}

/** Simboli verificati il 2026-11-05 sull'endpoint dati. */
export const INSTRUMENTS: Instrument[] = [
  { symbol: "CSPX.L", ticker: "CSPX", name: "iShares Core S&P 500", kind: "ETF", aliases: "sp500 usa america" },
  { symbol: "SWDA.MI", ticker: "SWDA", name: "iShares Core MSCI World", kind: "ETF", aliases: "mondo world globale" },
  { symbol: "MEUD.PA", ticker: "MEUD", name: "Amundi Core Stoxx Europe 600", kind: "ETF", aliases: "europa" },
  { symbol: "VWCE.DE", ticker: "VWCE", name: "Vanguard FTSE All-World", kind: "ETF", aliases: "mondo globale" },
  { symbol: "IUSQ.DE", ticker: "IUSQ", name: "iShares MSCI All Country World", kind: "ETF", aliases: "acwi mondo" },
  { symbol: "XDWD.DE", ticker: "XDWD", name: "Xtrackers MSCI World", kind: "ETF", aliases: "mondo" },
  { symbol: "EIMI.MI", ticker: "EIMI", name: "iShares Core MSCI EM IMI", kind: "ETF", aliases: "emergenti emerging" },
  { symbol: "EQQQ.MI", ticker: "EQQQ", name: "Invesco Nasdaq-100", kind: "ETF", aliases: "tecnologia tech" },
  { symbol: "AGGH.MI", ticker: "AGGH", name: "iShares Global Aggregate Bond", kind: "ETF", aliases: "obbligazioni bond" },
  { symbol: "SPY", ticker: "SPY", name: "SPDR S&P 500", kind: "ETF", aliases: "sp500 usa" },
  { symbol: "VOO", ticker: "VOO", name: "Vanguard S&P 500", kind: "ETF", aliases: "sp500 usa" },
  { symbol: "QQQ", ticker: "QQQ", name: "Invesco QQQ", kind: "ETF", aliases: "nasdaq tecnologia" },
  { symbol: "^GSPC", ticker: "SPX", name: "S&P 500", kind: "Indice", aliases: "sp500 usa" },
  { symbol: "^IXIC", ticker: "IXIC", name: "Nasdaq Composite", kind: "Indice", aliases: "tecnologia" },
  { symbol: "FTSEMIB.MI", ticker: "FTSEMIB", name: "FTSE MIB", kind: "Indice", aliases: "italia piazza affari milano" },
  { symbol: "^STOXX50E", ticker: "SX5E", name: "Euro Stoxx 50", kind: "Indice", aliases: "europa eurozona" },
  { symbol: "^STOXX", ticker: "SXXP", name: "Stoxx Europe 600", kind: "Indice", aliases: "europa" },
  { symbol: "^GDAXI", ticker: "DAX", name: "DAX", kind: "Indice", aliases: "germania" },
  { symbol: "^N225", ticker: "N225", name: "Nikkei 225", kind: "Indice", aliases: "giappone" },
];

export const DEFAULT_INSTRUMENT = INSTRUMENTS[0];

export function searchInstruments(text: string, limit = 6): Instrument[] {
  const term = text.trim().toLowerCase();
  if (term.length < 2) return [];
  const score = ({ ticker, name, aliases = "" }: Instrument) => {
    if (ticker.toLowerCase().startsWith(term)) return 0;
    if (name.toLowerCase().includes(term)) return 1;
    return aliases.includes(term) ? 2 : 3;
  };
  return INSTRUMENTS
    .map((instrument) => ({ instrument, rank: score(instrument) }))
    .filter(({ rank }) => rank < 3)
    .sort((first, second) => first.rank - second.rank)
    .slice(0, limit)
    .map(({ instrument }) => instrument);
}
