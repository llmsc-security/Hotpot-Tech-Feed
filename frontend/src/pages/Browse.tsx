import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  bumpItemClick,
  itemSuggestions,
  listHotItems,
  listItems,
  nlSearch,
  type NLFilter,
} from "../api";
import {
  BookmarkIcon,
  ChevronIcon,
  ExternalIcon,
  FlameIcon,
  SearchIcon,
  SparklesIcon,
  StarIcon,
} from "../components/HotpotIcons";
import ItemCard from "../components/ItemCard";
import { useConsent } from "../hooks/useConsent";
import type { HotItem, Item } from "../types";

const TIPS = [
  "ML papers from arxiv this year",
  "openai 2025 blog posts, newest first",
  "wechat: large model news",
  "中文安全：漏洞预警和复现",
  "Doonsec CVE warnings from WeChat",
  "robotics tutorials, oldest first",
  "security papers about transformer attention",
];

const FILTER_LABELS: Record<keyof NLFilter, string> = {
  topic: "topic",
  content_type: "type",
  source: "source",
  year: "year",
  q: "matches",
  sort: "sort",
};

type Filters = NLFilter;

const DEFAULT_FILTERS: Filters = { sort: "smart" };
const PAGE_SIZE = 25;

export default function Browse() {
  const [askInput, setAskInput] = useState<string>("");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [askError, setAskError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [suggestQuery, setSuggestQuery] = useState("");
  const [page, setPage] = useState(0);
  const inputWrapRef = useRef<HTMLDivElement | null>(null);
  const askInputRef = useRef<HTMLInputElement | null>(null);
  const qc = useQueryClient();
  const { consent, set: setConsent } = useConsent();

  const suggestions = useQuery({
    queryKey: ["item-suggestions", suggestQuery, consent],
    queryFn: () =>
      itemSuggestions(suggestQuery, {
        limit: 10,
        includeRecent: consent === "accepted",
      }),
    staleTime: 30_000,
    enabled: historyOpen,
  });

  const params = {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    topic: filters.topic ? `topic:${filters.topic}` : undefined,
    content_type: filters.content_type,
    source: filters.source,
    year: filters.year,
    q: filters.q,
    sort: filters.sort ?? "smart",
  };

  const items = useQuery({
    queryKey: ["items", params],
    queryFn: () => listItems(params),
  });

  const ask = useMutation({
    mutationFn: (q: string) => nlSearch(q, { record: consent === "accepted" }),
    onSuccess: (parsed) => {
      setAskError(null);
      const next: Filters = { sort: parsed.sort ?? "smart", ...parsed };
      if (!parsed.sort) next.sort = "smart";
      setFilters(next);
      setPage(0);
      const summary = describeFilters(next);
      setExplanation(summary || "no filters extracted - showing everything");
      qc.invalidateQueries({ queryKey: ["item-suggestions"] });
      setHistoryOpen(false);
    },
    onError: (err: Error) => {
      setAskError(err.message);
      setExplanation(null);
    },
  });

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (
        inputWrapRef.current &&
        !inputWrapRef.current.contains(e.target as Node)
      ) {
        setHistoryOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    function focusFromShell() {
      askInputRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
      askInputRef.current?.focus();
      setHistoryOpen(true);
    }
    function askFromShell(e: Event) {
      const query = String((e as CustomEvent<string>).detail ?? "").trim();
      if (!query) return;
      runAsk(query);
      askInputRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    window.addEventListener("hotpot:focus-ask", focusFromShell);
    window.addEventListener("hotpot:ask-query", askFromShell);
    return () => {
      window.removeEventListener("hotpot:focus-ask", focusFromShell);
      window.removeEventListener("hotpot:ask-query", askFromShell);
    };
  });

  useEffect(() => {
    const t = window.setTimeout(() => setSuggestQuery(askInput.trim()), 180);
    return () => window.clearTimeout(t);
  }, [askInput]);

  function runAsk(text?: string) {
    const v = (text ?? askInput).trim();
    if (!v || ask.isPending) return;
    if (text !== undefined) setAskInput(text);
    setPage(0);
    ask.mutate(v);
  }

  function removeFilter(key: keyof Filters) {
    const next = { ...filters };
    delete next[key];
    if (key === "sort") next.sort = "smart";
    setFilters(next);
    setPage(0);
    setExplanation(describeFilters(next) || "no filters - showing everything");
  }

  function clearAll() {
    setFilters(DEFAULT_FILTERS);
    setAskInput("");
    setAskError(null);
    setExplanation(null);
    setPage(0);
  }

  const activeChips = (Object.keys(filters) as (keyof Filters)[]).filter(
    (k) =>
      filters[k] !== undefined &&
      filters[k] !== "" &&
      !(k === "sort" && filters.sort === "smart"),
  );
  const showHot = activeChips.length === 0;

  const hotItems = useQuery({
    queryKey: ["hot-items", 20, 14],
    queryFn: () => listHotItems({ limit: 20, windowDays: 14 }),
    staleTime: 60_000,
    enabled: showHot,
  });

  return (
    <div className="gx-page-stack">
      <div className="gx-page-title">
        <div className="min-w-0">
          <div className="gx-title-row">
            <FlameIcon size={20} className="text-[var(--gx-chili)]" />
            <h1>Your hot list</h1>
            {showHot && (
              <span className="gx-chip gx-chip-chili hidden sm:inline-flex">
                {hotItems.data?.length ?? "..."} hot signals
              </span>
            )}
          </div>
          <p>
            Personalized by corpus repetition, freshness, source quality, and your search intent
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={`gx-chip ${filters.sort === "smart" ? "gx-chip-dark" : ""}`}
            onClick={() => {
              setFilters((cur) => ({ ...cur, sort: "smart" }));
              setPage(0);
            }}
          >
            Smart
          </button>
          <button
            type="button"
            className={`gx-chip ${filters.sort === "date_desc" ? "gx-chip-dark" : ""}`}
            onClick={() => {
              setFilters((cur) => ({ ...cur, sort: "date_desc" }));
              setPage(0);
            }}
          >
            Newest
          </button>
        </div>
      </div>

      <section className="gx-card-hero">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--gx-chili)]">
              <SparklesIcon size={13} />
              Ask Hotpot
            </p>
            <h2 className="gx-section-title text-xl font-bold text-[var(--gx-ink)] sm:text-2xl">
              Describe what you want. The agent builds the filters.
            </h2>
          </div>
          <span className="gx-chip gx-chip-amber text-[11px]">LLM search</span>
        </div>

        <div ref={inputWrapRef} className="relative flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <SearchIcon
              size={17}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--gx-muted)]"
            />
            <input
              ref={askInputRef}
              type="text"
              value={askInput}
              onChange={(e) => {
                setAskInput(e.target.value);
                setHistoryOpen(true);
              }}
              onFocus={() => setHistoryOpen(true)}
              onKeyDown={(e) => {
                if (e.key === "Enter") runAsk();
                if (e.key === "Escape") setHistoryOpen(false);
              }}
              placeholder="papers on KV cache compression this year"
              className="w-full rounded-full border border-[var(--gx-line)] bg-white py-3 pl-10 pr-4 text-sm text-[var(--gx-ink)]
                         shadow-sm outline-none transition focus:border-[var(--gx-chili)]
                         focus:ring-4 focus:ring-[rgba(200,68,44,0.10)]"
            />
          </div>
          <button
            type="button"
            onClick={() => runAsk()}
            disabled={!askInput.trim() || ask.isPending}
            className="gx-btn gx-btn-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            <SparklesIcon size={14} />
            {ask.isPending ? "Thinking..." : "Apply"}
          </button>

          {historyOpen && suggestions.data && suggestions.data.length > 0 && (
            <div
              className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 max-h-72 overflow-y-auto rounded-xl
                         border border-[var(--gx-line)] bg-white text-sm shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-[var(--gx-line-2)] px-4 py-2 text-[10px] uppercase tracking-wide text-[var(--gx-muted)]">
                <span>suggestions</span>
                <span>esc to close</span>
              </div>
              {suggestions.data.slice(0, 12).map((s) => (
                <button
                  key={s.type + s.query}
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    runAsk(s.query);
                  }}
                  className="flex w-full items-center gap-3 border-b border-[var(--gx-line-2)] px-4 py-2 text-left last:border-0 hover:bg-[var(--gx-surface-2)]"
                >
                  <span className="w-20 shrink-0 text-[10px] uppercase tracking-wide text-[var(--gx-muted)]">
                    {formatSuggestionType(s.type)}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-medium text-[var(--gx-ink)]">
                    {s.label}
                  </span>
                  <span className="hidden max-w-[38%] truncate text-xs text-[var(--gx-muted)] sm:inline">
                    {s.detail ?? s.query}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--gx-muted)]">
          <span>try:</span>
          {TIPS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => runAsk(t)}
              className="gx-chip bg-white text-[11px] font-medium hover:border-[var(--gx-chili)]"
            >
              {t}
            </button>
          ))}
        </div>

        <ConsentLine consent={consent} setConsent={setConsent} />
        {askError && <p className="mt-3 text-xs text-red-700">{askError}</p>}
        {explanation && (
          <p className="mt-3 text-xs text-[var(--gx-muted)]">
            <span className="text-[var(--gx-chili)]">{"->"}</span> {explanation}
          </p>
        )}
      </section>

      {activeChips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-[var(--gx-muted)]">filters:</span>
          {activeChips.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => removeFilter(k)}
              className="gx-chip gx-chip-chili group"
              title="click to remove"
            >
              <span className="opacity-70">{FILTER_LABELS[k]}:</span>
              <span className="max-w-[180px] truncate">{String(filters[k])}</span>
              <span className="opacity-60 group-hover:opacity-100">x</span>
            </button>
          ))}
          <button
            type="button"
            onClick={clearAll}
            className="text-xs text-[var(--gx-muted)] underline underline-offset-2 hover:text-[var(--gx-ink)]"
          >
            clear
          </button>
        </div>
      )}

      {showHot && (
        <HotNewsPanel hotItems={hotItems.data ?? []} isLoading={hotItems.isLoading} />
      )}

      <section className="gx-card p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--gx-muted)]">
              feed
            </p>
            <h2 className="gx-section-title text-xl font-bold text-[var(--gx-ink)]">
              {activeChips.length > 0 ? "Filtered results" : "Latest from the corpus"}
            </h2>
          </div>
          {items.data && <CorpusPagerLabel total={items.data.total} page={page} count={items.data.items.length} />}
        </div>

        {items.isLoading && <p className="text-sm text-[var(--gx-muted)]">Loading...</p>}
        {items.error && (
          <p className="text-sm text-red-700">Failed to load items. Is the backend reachable?</p>
        )}

        {items.data && (
          <>
            <div className="grid gap-3">
              {items.data.items.map((it) => (
                <ItemCard key={it.id} item={it} />
              ))}
            </div>
            {items.data.items.length === 0 && (
              <p className="mt-8 text-sm text-[var(--gx-muted)]">
                No items match these filters. Remove a chip or ask something different.
              </p>
            )}
            <CorpusPager
              total={items.data.total}
              page={page}
              count={items.data.items.length}
              onPage={setPage}
            />
          </>
        )}
      </section>
    </div>
  );
}

function CorpusPagerLabel({
  total,
  page,
  count,
}: {
  total: number;
  page: number;
  count: number;
}) {
  if (total === 0) {
    return <span className="text-xs text-[var(--gx-muted)]">0 items</span>;
  }
  const start = page * PAGE_SIZE + 1;
  const end = Math.min(page * PAGE_SIZE + count, total);
  return (
    <span className="text-xs text-[var(--gx-muted)]">
      {start}-{end} of {total} items
    </span>
  );
}

function CorpusPager({
  total,
  page,
  count,
  onPage,
}: {
  total: number;
  page: number;
  count: number;
  onPage: (page: number) => void;
}) {
  const canPrev = page > 0;
  const canNext = page * PAGE_SIZE + count < total;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  if (total <= PAGE_SIZE && page === 0) return null;

  return (
    <div className="mt-5 flex items-center justify-between gap-3">
      <button
        type="button"
        onClick={() => onPage(Math.max(0, page - 1))}
        disabled={!canPrev}
        className="gx-btn disabled:cursor-not-allowed disabled:opacity-40"
      >
        Previous
      </button>
      <span className="text-xs text-[var(--gx-muted)]">
        Page {page + 1} of {totalPages}
      </span>
      <button
        type="button"
        onClick={() => onPage(page + 1)}
        disabled={!canNext}
        className="gx-btn disabled:cursor-not-allowed disabled:opacity-40"
      >
        Next
      </button>
    </div>
  );
}

function ConsentLine({
  consent,
  setConsent,
}: {
  consent: string | null;
  setConsent: (value: "accepted" | "rejected") => void;
}) {
  return (
    <p className="mt-3 text-[11px] leading-relaxed text-[var(--gx-muted)]">
      {consent === "accepted" ? (
        <>
          Query logging is on for search improvement.{" "}
          <button
            type="button"
            onClick={() => setConsent("rejected")}
            className="font-semibold text-[var(--gx-chili)] underline underline-offset-2"
          >
            opt out
          </button>
        </>
      ) : consent === "rejected" ? (
        <>
          Query logging is off. Source, topic, and title suggestions still work.{" "}
          <button
            type="button"
            onClick={() => setConsent("accepted")}
            className="font-semibold text-[var(--gx-chili)] underline underline-offset-2"
          >
            opt in
          </button>
        </>
      ) : (
        <>Choose a consent option below to decide whether searches can be saved.</>
      )}
    </p>
  );
}

function HotNewsPanel({
  hotItems,
  isLoading,
}: {
  hotItems: HotItem[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <section className="gx-card p-5">
        <p className="text-sm text-[var(--gx-muted)]">Loading hot repeated stories...</p>
      </section>
    );
  }
  if (hotItems.length === 0) return null;

  const featured = hotItems[0];
  const rows = hotItems.slice(1, 7);
  const rail = hotItems.slice(7, 12);

  return (
    <section className="grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0 space-y-4">
        <FeaturedHotItem hot={featured} />

        <div className="flex flex-wrap items-center gap-2">
          <span className="gx-chip gx-chip-dark">Smart</span>
          <span className="gx-chip">Newest</span>
          <span className="gx-chip">Most discussed</span>
          <span className="gx-chip">Group threads</span>
          <span className="ml-auto text-xs text-[var(--gx-muted)]">
            Showing 1-{Math.min(hotItems.length, 7)} of {hotItems.length}
          </span>
        </div>

        <div className="grid gap-2">
          {rows.map((hot, index) => (
            <HotRow key={hot.item.id} hot={hot} rank={index + 2} />
          ))}
        </div>
      </div>

      <aside className="min-w-0 overflow-hidden">
        <div className="mb-3">
          <div className="flex items-center gap-2">
            <FlameIcon size={15} className="text-[var(--gx-chili)]" />
            <h3 className="gx-section-title m-0 text-lg font-bold">Trending elsewhere</h3>
          </div>
          <p className="m-0 text-xs text-[var(--gx-muted)]">
            High-repeat stories outside the top slice
          </p>
        </div>
        <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
          {rail.map((hot, index) => (
            <TrendingCard key={hot.item.id} hot={hot} rank={index + 1} />
          ))}
        </div>
      </aside>
    </section>
  );
}

function FeaturedHotItem({ hot }: { hot: HotItem }) {
  const item = hot.item;
  const topic = hot.topic || topicFromItem(item);
  const excerpt = item.summary ?? item.excerpt;
  const date = dateText(item.published_at ?? item.fetched_at);

  return (
    <article className="gx-card-hero">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="gx-chip gx-chip-chili">
          <StarIcon size={12} filled />
          Top for you
        </span>
        {topic && <span className="gx-chip">{topic}</span>}
        <span className="gx-chip gx-chip-chili">Trending - {hot.source_count} sources</span>
        <span className="ml-auto text-xs text-[var(--gx-muted)]">{item.source_name ?? "source"} - {date}</span>
      </div>

      <h2 className="gx-section-title mb-2 text-2xl font-bold leading-tight text-[var(--gx-ink)]">
        <a
          href={item.canonical_url}
          target="_blank"
          rel="noreferrer"
          className="hover:text-[var(--gx-chili)]"
          onClick={() => bumpItemClick(item.id)}
          onAuxClick={(e) => {
            if (e.button === 1) bumpItemClick(item.id);
          }}
        >
          {item.title}
        </a>
      </h2>
      {excerpt && (
        <p className="mb-4 max-w-4xl text-sm leading-relaxed text-[var(--gx-ink-2)]">
          {excerpt}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="gx-why-line">
          {"->"} {hot.support_count} exposures - {hot.source_count} sources - score {hot.hot_score.toFixed(2)}
        </span>
        <span className="flex-1" />
        <button
          type="button"
          className="gx-btn"
          disabled
          title="Saved lists are not implemented yet"
        >
          <BookmarkIcon size={13} />
          Save
        </button>
        <a
          href={item.canonical_url}
          target="_blank"
          rel="noreferrer"
          className="gx-btn gx-btn-primary"
          onClick={() => bumpItemClick(item.id)}
        >
          Read
          <ExternalIcon size={13} />
        </a>
      </div>
    </article>
  );
}

function HotRow({ hot, rank }: { hot: HotItem; rank: number }) {
  const item = hot.item;
  const topic = hot.topic || topicFromItem(item);
  return (
    <article className="gx-row-card">
      <span className="gx-rank gx-rank-dark">{rank}</span>
      <div className="min-w-0 flex-1">
        <h3 className="line-clamp-2 text-[14.5px] font-bold leading-snug text-[var(--gx-ink)]">
          <a
            href={item.canonical_url}
            target="_blank"
            rel="noreferrer"
            className="hover:text-[var(--gx-chili)]"
            onClick={() => bumpItemClick(item.id)}
            onAuxClick={(e) => {
              if (e.button === 1) bumpItemClick(item.id);
            }}
          >
            {item.title}
          </a>
        </h3>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {topic && <span className="gx-chip px-2 py-0.5 text-[11px]">{topic}</span>}
          <span className="gx-why-line">
            {"->"} {hot.source_count} sources covering it
          </span>
        </div>
      </div>
      <span className="shrink-0 font-mono text-[11px] text-[var(--gx-muted)]">
        {dateText(item.published_at ?? item.fetched_at)}
      </span>
      <FlameIcon size={14} className="text-[var(--gx-chili)]" />
      <ChevronIcon size={14} className="text-[var(--gx-muted)]" />
    </article>
  );
}

function TrendingCard({ hot, rank }: { hot: HotItem; rank: number }) {
  const item = hot.item;
  const topic = hot.topic || topicFromItem(item) || "General";
  const sourceTitle = hot.sources.length ? hot.sources.join(", ") : "source unknown";
  return (
    <article className="gx-trend-card min-w-0">
      <div className="mb-2 flex items-center gap-2">
        <span className="gx-rank h-5 w-5 flex-[0_0_20px] text-[10px]">{rank}</span>
        <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--gx-muted)]">
          {topic} - x{hot.source_count}
        </span>
        <span className="font-mono text-[11px] font-bold text-[var(--gx-chili)]">
          {hot.hot_score.toFixed(2)}
        </span>
      </div>
      <a
        href={item.canonical_url}
        target="_blank"
        rel="noreferrer"
        title={sourceTitle}
        className="line-clamp-2 text-sm font-semibold leading-snug hover:text-[var(--gx-chili)]"
        onClick={() => bumpItemClick(item.id)}
      >
        {item.title}
      </a>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {hot.sources.slice(0, 2).map((source) => (
          <span key={source} className="gx-chip px-2 py-0.5 text-[10px]" title={source}>
            {source}
          </span>
        ))}
      </div>
    </article>
  );
}

function topicFromItem(item: Item): string | null {
  return item.tags.find((t) => t.tag.startsWith("topic:"))?.tag.slice(6) ?? item.primary_category;
}

function dateText(value: string | null): string {
  if (!value) return "unknown";
  return value.slice(0, 10);
}

function describeFilters(f: Filters): string {
  const parts: string[] = [];
  if (f.topic) parts.push(`topic = ${f.topic}`);
  if (f.content_type) parts.push(`type = ${f.content_type}`);
  if (f.source) parts.push(`source ~ ${f.source}`);
  if (f.year) parts.push(`year = ${f.year}`);
  if (f.q) parts.push(`matches ~ ${f.q}`);
  if (f.sort && f.sort !== "smart") parts.push(`sort = ${f.sort}`);
  return parts.join(" - ");
}

function formatSuggestionType(type: string): string {
  if (type === "recent_query") return "recent";
  return type.replace("_", " ");
}
