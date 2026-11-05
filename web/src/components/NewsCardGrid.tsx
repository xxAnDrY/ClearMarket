import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, type ReactNode } from "react";
import { fetchCategories, fetchFeed, type FeedQuery } from "../api";
import { NewsCard, NewsCardSkeleton } from "./NewsCard";

const REFRESH_MS = 5 * 60_000; // in linea con il polling del worker
const GRID = "grid grid-flow-dense gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-2";

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: ({ signal }) => fetchCategories(signal),
    staleTime: Infinity,
  }).data ?? [];
}

interface NewsCardGridProps {
  query: FeedQuery;
  onTicker?: (ticker: string) => void;
  empty?: ReactNode;
}

export function NewsCardGrid({ query, onTicker, empty }: NewsCardGridProps) {
  const categories = useCategories();
  const feed = useInfiniteQuery({
    queryKey: ["feed", query],
    queryFn: ({ pageParam, signal }) => fetchFeed(query, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => (page.page_info.has_more ? page.page_info.next_cursor : null),
    refetchInterval: REFRESH_MS,
  });

  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = feed;
  useEffect(() => {
    const node = sentinel.current;
    // Dopo un errore si riprende solo col pulsante, per non ritentare a ogni scroll.
    if (!node || !hasNextPage || isFetchingNextPage || isFetchNextPageError) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void fetchNextPage();
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage]);

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

  const articles = feed.data?.pages.flatMap((page) => page.data) ?? [];
  // Una pagina puo' sovrapporsi a un refetch: la chiave React deve restare unica.
  const unique = [...new Map(articles.map((article) => [article.id, article])).values()];
  if (unique.length === 0) {
    return <>{empty ?? <p className="rounded-2xl border border-line bg-surface px-4 py-16 text-center text-muted shadow-sm">Nessuna notizia trovata.</p>}</>;
  }

  return (
    <>
      <div className={GRID}>
        {unique.map((article, index) => (
          <NewsCard key={article.id} article={article} categories={categories} featured={index === 0} onTicker={onTicker} />
        ))}
      </div>
      <div ref={sentinel} className="py-6 text-center text-sm text-muted">
        {feed.isFetchNextPageError ? (
          <button onClick={() => void feed.fetchNextPage()} className="tactile font-semibold text-accent">
            Caricamento non riuscito. Riprova
          </button>
        ) : feed.hasNextPage ? "Caricamento…" : "Sei aggiornato"}
      </div>
    </>
  );
}
