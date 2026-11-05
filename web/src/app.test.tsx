import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { feedParams, safeUrl, type Article } from "./api";
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
    render(<NewsCard article={article} categories={[{ slug: "monetary_policy", label: "Politica monetaria" }]} />);
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
    render(<NewsCard article={article} categories={[]} onTicker={onTicker} />);
    fireEvent.click(screen.getByRole("button", { name: "Cerca AAPL" }));
    expect(onTicker).toHaveBeenCalledWith("AAPL");
    expect(screen.getByRole("link").contains(screen.getByRole("button"))).toBe(false);
  });

  it("non crea link per schemi pericolosi", () => {
    render(<NewsCard article={{ ...article, source_url: "javascript:alert(1)" }} categories={[]} />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("feedParams", () => {
  it("Tutte non filtra, una pillola invia le sue categorie e la ricerca", () => {
    expect(feedParams({ kind: "all", categories: [], search: "" }, null).toString()).toBe("limit=20");
    const filtered = feedParams({ kind: "all", categories: ["macro", "microeconomics"], search: "spread" }, null);
    expect(filtered.getAll("category")).toEqual(["macro", "microeconomics"]);
    expect(filtered.get("q")).toBe("spread");
  });

  it("la watchlist chiede ticker oppure categorie e porta il cursore", () => {
    const params = feedParams({ kind: "watchlist", tickers: ["AAPL", "BTC"], categories: ["etf"] }, "abc");
    expect(params.get("match")).toBe("any");
    expect(params.getAll("ticker")).toEqual(["AAPL", "BTC"]);
    expect(params.get("cursor")).toBe("abc");
  });

  it("le pillole coprono i temi richiesti", () => {
    expect(FILTERS.map(({ label }) => label)).toEqual(expect.arrayContaining(
      ["Tutte", "Macro", "Governo & Fisco", "BCE/FED", "Mercati UE", "USA", "Crypto"]));
  });
});

describe("utilita'", () => {
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
