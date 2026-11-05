import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchFeed, filterArticles, type NewsQuery } from "../api";
import { NewsCard, NewsCardSkeleton } from "./NewsCard";

const REFRESH_MS = 5 * 60_000;
const PAGE_SIZE = 24;
const GRID = "grid grid-flow-dense gap-3 md:grid-cols-2";

export function NewsCardGrid({ query, onTicker }: { query: NewsQuery; onTicker?: (ticker: string) => void }) {
  const feed = useQuery({
    queryKey: ["feed"],
    queryFn: ({ signal }) => fetchFeed(signal),
    refetchInterval: REFRESH_MS,
  });

  const articles = useMemo(() => filterArticles(feed.data?.articles ?? [], query), [feed.data, query]);

  const [shown, setShown] = useState(PAGE_SIZE);
  useEffect(() => setShown(PAGE_SIZE), [query]);

  const sentinel = useRef<HTMLDivElement>(null);
  const hasMore = shown < articles.length;
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setShown((count) => count + PAGE_SIZE);
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, shown]);

  if (feed.isPending) {
    return (
      <div role="status" aria-label="Caricamento notizie" className={GRID}>
        {Array.from({ length: 7 }, (_, index) => <NewsCardSkeleton key={index} featured={index === 0} />)}
      </div>
    );
  }

  if (feed.isError && !feed.data) {
    return (
      <div className="rounded-2xl border border-line bg-surface px-4 py-16 text-center shadow-sm">
        <p className="text-muted">{feed.error.message}</p>
        <button onClick={() => void feed.refetch()} className="tactile mt-3 rounded-full bg-accent px-5 py-2 text-sm font-semibold text-on-accent">
          Riprova
        </button>
      </div>
    );
  }

  if (articles.length === 0) {
    return <p className="rounded-2xl border border-line bg-surface px-4 py-16 text-center text-muted shadow-sm">Nessuna notizia trovata.</p>;
  }

  return (
    <>
      <div className={GRID}>
        {articles.slice(0, shown).map((article, index) => (
          <NewsCard key={article.id} article={article} featured={index === 0} onTicker={onTicker} />
        ))}
      </div>
      <div ref={sentinel} className="py-6 text-center text-sm text-muted">
        {hasMore ? "Caricamento…" : "Sei aggiornato"}
      </div>
    </>
  );
}
