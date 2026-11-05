import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { eventsOn, filterArticles, isMarketOpen, safeUrl, type Article, type EconomicEvent } from "./api";
import { FILTERS } from "./components/FilterTabs";
import { NewsCard } from "./components/NewsCard";
import { normalizeTicker } from "./preferences";
import { relativeTime } from "./time";

afterEach(cleanup);

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

  it("Tutte mostra ogni notizia, una pillola filtra per categoria", () => {
    expect(ids(filterArticles([article, other], { kind: "all", categories: [], search: "" }))).toEqual(["1", "2"]);
    expect(ids(filterArticles([article, other], { kind: "all", categories: ["crypto"], search: "" }))).toEqual(["2"]);
  });

  it("la ricerca guarda testo e ticker", () => {
    expect(ids(filterArticles([article, other], { kind: "all", categories: [], search: "bce" }))).toEqual(["1"]);
    expect(ids(filterArticles([article, other], { kind: "all", categories: [], search: "btc" }))).toEqual(["2"]);
  });

  it("la watchlist vuole un ticker oppure una categoria", () => {
    expect(ids(filterArticles([article, other], { kind: "watchlist", tickers: ["BTC"], categories: ["monetary_policy"] }))).toEqual(["1", "2"]);
    expect(ids(filterArticles([article, other], { kind: "watchlist", tickers: [], categories: [] }))).toEqual([]);
  });

  it("le pillole coprono i temi richiesti", () => {
    expect(FILTERS.map(({ label }) => label)).toEqual(expect.arrayContaining(
      ["Tutte", "Macro", "Governo & Fisco", "BCE/FED", "Mercati UE", "USA", "Crypto"]));
  });
});

describe("utilita'", () => {
  it("isMarketOpen usa l'ora di Roma", () => {
    expect(isMarketOpen(new Date("2026-11-05T10:00:00Z"))).toBe(true);   // giovedi' 11:00
    expect(isMarketOpen(new Date("2026-11-05T07:00:00Z"))).toBe(false);  // 08:00
    expect(isMarketOpen(new Date("2026-11-05T22:00:00Z"))).toBe(false);  // 23:00
    expect(isMarketOpen(new Date("2026-11-07T10:00:00Z"))).toBe(false);  // sabato
  });

  it("eventsOn seleziona il giorno locale", () => {
    const event = { starts_at: new Date(2026, 10, 5, 23, 30).toISOString() } as EconomicEvent;
    expect(eventsOn([event], new Date(2026, 10, 5))).toHaveLength(1);
    expect(eventsOn([event], new Date(2026, 10, 6))).toHaveLength(0);
  });

  it("safeUrl accetta solo http e https", () => {
    expect(safeUrl("https://a.it/x")).toBe("https://a.it/x");
    expect(safeUrl("data:text/html,x")).toBeUndefined();
    expect(safeUrl("non un url")).toBeUndefined();
  });

  it("normalizeTicker pulisce e valida", () => {
    expect(normalizeTicker(" $aapl ")).toBe("AAPL");
    expect(normalizeTicker("ucg.mi")).toBe("UCG.MI");
    expect(normalizeTicker("bad ticker")).toBeNull();
  });

  it("relativeTime compatto", () => {
    const now = Date.parse("2026-11-05T12:00:00Z");
    expect(relativeTime("2026-11-05T11:55:00Z", now)).toBe("5m fa");
    expect(relativeTime("2026-11-05T09:00:00Z", now)).toBe("3h fa");
    expect(relativeTime("2026-11-03T09:00:00Z", now)).toBe("2g fa");
    expect(relativeTime("2026-11-05T12:00:10Z", now)).toBe("adesso");
  });
});
