import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import chart from "../netlify/functions/chart";
import movers from "../netlify/functions/movers";
import { filterArticles, isMarketOpen, safeUrl, type Article } from "./api";
import { FILTERS } from "./components/FilterTabs";
import { InstrumentSearch } from "./components/InstrumentSearch";
import { NewsCard } from "./components/NewsCard";
import { formatPrice } from "./format";
import { searchInstruments } from "./instruments";
import { relativeTime } from "./time";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const article: Article = {
  id: "1",
  title: "La Bce lascia i tassi invariati",
  summary: "Sommario",
  source: { slug: "ansa", name: "ANSA Economia" },
  source_url: "https://example.com/a",
  translated: true,
  published_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  category: "monetary_policy",
  related_tickers: ["AAPL"],
  sentiment: { label: "negative", score: -0.4 },
};

describe("NewsCard", () => {
  it("apre la fonte in una nuova scheda e mostra i metadati", () => {
    render(<NewsCard article={article} />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("https://example.com/a");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    for (const text of ["· Tradotto", "AAPL", "Sentiment negativo", "Politica monetaria", "ANSA Economia"]) {
      expect(screen.getByText(text)).toBeTruthy();
    }
  });

  it("il ticker cerca senza aprire la fonte", () => {
    const onTicker = vi.fn();
    render(<NewsCard article={article} onTicker={onTicker} />);
    fireEvent.click(screen.getByRole("button", { name: "Cerca AAPL" }));
    expect(onTicker).toHaveBeenCalledWith("AAPL");
    expect(screen.getByRole("link").contains(screen.getByRole("button"))).toBe(false);
  });

  it("non crea link per schemi pericolosi", () => {
    render(<NewsCard article={{ ...article, source_url: "javascript:alert(1)" }} />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("filterArticles", () => {
  const other: Article = { ...article, id: "2", title: "Bitcoin in calo", summary: "", category: "crypto", related_tickers: ["BTC"] };
  const ids = (result: Article[]) => result.map(({ id }) => id);

  it("filtra per categoria e cerca in testo e ticker", () => {
    expect(ids(filterArticles([article, other], { categories: [], search: "" }))).toEqual(["1", "2"]);
    expect(ids(filterArticles([article, other], { categories: ["crypto"], search: "" }))).toEqual(["2"]);
    expect(ids(filterArticles([article, other], { categories: [], search: "bce" }))).toEqual(["1"]);
    expect(ids(filterArticles([article, other], { categories: [], search: "btc" }))).toEqual(["2"]);
  });

  it("le pillole sono quelle richieste", () => {
    expect(FILTERS.map(({ label }) => label)).toEqual(["Tutte", "Macro", "Governo & Fisco", "BCE/FED", "Mercati UE/USA"]);
  });
});

describe("ricerca ETF", () => {
  it("trova ticker, nomi e alias", () => {
    expect(searchInstruments("cspx")[0].symbol).toBe("CSPX.L");
    expect(searchInstruments("swda")[0].symbol).toBe("SWDA.MI");
    expect(searchInstruments("stoxx").map(({ ticker }) => ticker)).toContain("MEUD");
    expect(searchInstruments("emergenti")[0].ticker).toBe("EIMI");
    expect(searchInstruments("c")).toEqual([]);
  });

  it("si usa da tastiera", () => {
    const onSelect = vi.fn();
    render(<InstrumentSearch value="mondo" onChange={() => {}} onSelect={onSelect} label="Cerca" placeholder="" />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect.mock.calls[0][0].ticker).toBe("VWCE");
  });
});

describe("funzioni dati", () => {
  const meta = { symbol: "CSPX.L", longName: "iShares", currency: "USD", regularMarketPrice: 110, previousClose: 100, regularMarketTime: 1793896527 };
  const stubFetch = (body: unknown, status = 200) => {
    const fetchMock = vi.fn(async (_url: string) => new Response(JSON.stringify(body), { status }));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  };

  it("chart scarta i punti vuoti e calcola la variazione", async () => {
    const fetchMock = stubFetch({ chart: { result: [{ meta, timestamp: [1, 2, 3], indicators: { quote: [{ close: [100, null, 110] }] } }] } });
    const response = await chart(new Request("http://x/api/chart?symbol=CSPX.L&range=1D"));
    const body = await response.json();
    expect(body.points).toEqual([{ time: 1, value: 100 }, { time: 3, value: 110 }]);
    expect(body.change_pct).toBe(10);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/CSPX.L?range=1d&interval=5m");
  });

  it("chart rifiuta richieste non valide senza chiamare Yahoo", async () => {
    const fetchMock = stubFetch({});
    expect((await chart(new Request("http://x/api/chart?symbol=../../etc&range=1D"))).status).toBe(400);
    expect((await chart(new Request("http://x/api/chart?symbol=SPY&range=5Y"))).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("un errore della fonte non diventa un dato", async () => {
    stubFetch({}, 429);
    expect((await chart(new Request("http://x/api/chart?symbol=SPY&range=1D"))).status).toBe(502);
    expect((await movers()).status).toBe(502);
  });

  it("movers ordina per variazione assoluta e tiene i primi tre", async () => {
    const item = (symbol: string, price: number) => ({ symbol, response: [{ meta: { ...meta, symbol, regularMarketPrice: price } }] });
    stubFetch({ spark: { result: [item("AAPL", 101), item("NVDA", 90), item("ENI.MI", 105), item("TSLA", 98), item("META", 100)] } });
    const body = await (await movers()).json();
    expect(body.movers.map(({ label }: { label: string }) => label)).toEqual(["Nvidia", "Eni", "Tesla"]);
    expect(body.movers[0].change_pct).toBe(-10);
  });
});

describe("utilita'", () => {
  it("isMarketOpen usa l'ora di Roma", () => {
    expect(isMarketOpen(new Date("2026-11-05T10:00:00Z"))).toBe(true);   // giovedi' 11:00
    expect(isMarketOpen(new Date("2026-11-05T07:00:00Z"))).toBe(false);  // 08:00
    expect(isMarketOpen(new Date("2026-11-05T22:00:00Z"))).toBe(false);  // 23:00
    expect(isMarketOpen(new Date("2026-11-07T10:00:00Z"))).toBe(false);  // sabato
  });

  it("safeUrl accetta solo http e https", () => {
    expect(safeUrl("https://a.it/x")).toBe("https://a.it/x");
    expect(safeUrl("data:text/html,x")).toBeUndefined();
  });

  it("formatPrice gestisce valute e pence", () => {
    expect(formatPrice(807.58, "USD")).toContain("807,58");
    expect(formatPrice(10637, "GBp")).toContain("p");
  });

  it("relativeTime compatto", () => {
    const now = Date.parse("2026-11-05T12:00:00Z");
    expect(relativeTime("2026-11-05T11:55:00Z", now)).toBe("5m fa");
    expect(relativeTime("2026-11-05T09:00:00Z", now)).toBe("3h fa");
    expect(relativeTime("2026-11-05T12:00:10Z", now)).toBe("adesso");
  });
});
