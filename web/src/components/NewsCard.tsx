import { CATEGORIES, safeUrl, type Article } from "../api";
import { relativeTime } from "../time";
import { ArrowIcon } from "./icons";

interface NewsCardProps {
  article: Article;
  featured?: boolean;
  onTicker?: (ticker: string) => void;
}

const SENTIMENT = {
  positive: { mark: "▲", label: "Sentiment positivo", color: "text-up" },
  negative: { mark: "▼", label: "Sentiment negativo", color: "text-down" },
};

export function NewsCard({ article, featured = false, onTicker }: NewsCardProps) {
  const href = safeUrl(article.source_url);
  const category = CATEGORIES[article.category];
  const sentiment = article.sentiment.label === "neutral" ? null : SENTIMENT[article.sentiment.label];
  const titleClass = `${featured ? "text-xl lg:text-2xl" : "text-base"} line-clamp-3 font-semibold leading-snug tracking-tight text-text transition-colors duration-200 group-hover:text-accent`;

  return (
    <article className={`group relative flex animate-fade-in flex-col rounded-2xl border border-line bg-surface p-4 shadow-sm transition-all duration-300 ease-soft hover:-translate-y-1 hover:border-glow hover:shadow-md ${featured ? "md:col-span-2" : ""}`}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        {category && <span className="rounded-full bg-accent/10 px-2 py-0.5 font-semibold text-accent">{category}</span>}
        <span title={article.language === "it" ? "Italiano" : "Inglese"} className="rounded border border-line px-1 text-[10px] font-semibold tracking-wide uppercase">{article.language}</span>
        <span className="font-medium text-text/80">{article.source.name}</span>
        <span aria-hidden="true">•</span>
        <time dateTime={article.published_at}>{relativeTime(article.published_at)}</time>
        {sentiment && (
          <span title={sentiment.label} className={sentiment.color}>
            <span aria-hidden="true">{sentiment.mark}</span>
            <span className="sr-only">{sentiment.label}</span>
          </span>
        )}
      </p>

      <h2 className={`mt-2 ${titleClass}`}>
        {href ? (
          // Il link si estende a tutta la card; i ticker restano cliccabili sopra di esso.
          <a href={href} target="_blank" rel="noopener noreferrer" className="outline-none after:absolute after:inset-0 after:rounded-2xl focus-visible:after:outline-2 focus-visible:after:outline-accent">
            {article.title}
          </a>
        ) : article.title}
      </h2>

      {article.summary && (
        <p className={`mt-1.5 text-sm leading-relaxed text-muted ${featured ? "line-clamp-3" : "line-clamp-2"}`}>{article.summary}</p>
      )}

      <div className="mt-auto flex items-end justify-between gap-2 pt-3">
        <div className="flex min-w-0 flex-wrap gap-1">
          {article.related_tickers.slice(0, 4).map((ticker) => (
            <button
              key={ticker}
              aria-label={`Cerca ${ticker}`}
              onClick={() => onTicker?.(ticker)}
              className="tactile relative z-10 rounded-full bg-raised px-2 py-0.5 text-[11px] font-semibold text-text tabular-nums hover:bg-accent hover:text-on-accent"
            >
              {ticker}
            </button>
          ))}
        </div>
        {href && (
          <ArrowIcon className="size-4 shrink-0 text-muted opacity-40 transition-all duration-300 ease-soft group-hover:translate-x-1 group-hover:text-accent group-hover:opacity-100" />
        )}
      </div>
    </article>
  );
}

export function NewsCardSkeleton({ featured = false }: { featured?: boolean }) {
  return (
    <div className={`rounded-2xl border border-line bg-surface p-4 shadow-sm ${featured ? "md:col-span-2" : ""}`} aria-hidden="true">
      <div className="skeleton h-4 w-40" />
      <div className="skeleton mt-3.5 h-4 w-full" />
      <div className="skeleton mt-2 h-4 w-3/4" />
      <div className="skeleton mt-3.5 h-3 w-full" />
      <div className="skeleton mt-2 h-3 w-5/6" />
    </div>
  );
}
