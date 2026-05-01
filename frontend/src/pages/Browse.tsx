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
import ItemCard from "../components/ItemCard";
import { useConsent } from "../hooks/useConsent";
import type { HotItem } from "../types";

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

export default function Browse() {
  const [askInput, setAskInput] = useState<string>("");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [askError, setAskError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [suggestQuery, setSuggestQuery] = useState("");
  const inputWrapRef = useRef<HTMLDivElement | null>(null);
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
    limit: 50,
    offset: 0,
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
      // Each Ask is a full replacement: the LLM saw the whole user intent.
      // sort defaults to smart when the user didn't specify.
      const next: Filters = { sort: parsed.sort ?? "smart", ...parsed };
      if (!parsed.sort) next.sort = "smart";
      setFilters(next);
      const summary = describeFilters(next);
      setExplanation(summary || "no filters extracted — showing everything");
      // The backend may have logged this query, so refresh typeahead recall.
      qc.invalidateQueries({ queryKey: ["item-suggestions"] });
      setHistoryOpen(false);
    },
    onError: (err: Error) => {
      setAskError(err.message);
      setExplanation(null);
    },
  });

  // Close the history dropdown when clicking outside the input area.
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

  function runAsk(text?: string) {
    const v = (text ?? askInput).trim();
    if (!v || ask.isPending) return;
    if (text !== undefined) setAskInput(text);
    ask.mutate(v);
  }

  function removeFilter(key: keyof Filters) {
    const next = { ...filters };
    delete next[key];
    if (key === "sort") next.sort = "smart";
    setFilters(next);
    setExplanation(describeFilters(next) || "no filters — showing everything");
  }

  function clearAll() {
    setFilters(DEFAULT_FILTERS);
    setAskInput("");
    setAskError(null);
    setExplanation(null);
  }

  const activeChips = (Object.keys(filters) as (keyof Filters)[])
    .filter((k) => filters[k] !== undefined && filters[k] !== "" &&
                   !(k === "sort" && filters.sort === "smart"));
  const showHot = activeChips.length === 0;

  const hotItems = useQuery({
    queryKey: ["hot-items", 20, 14],
    queryFn: () => listHotItems({ limit: 20, windowDays: 14 }),
    staleTime: 60_000,
    enabled: showHot,
  });

  useEffect(() => {
    const t = window.setTimeout(() => setSuggestQuery(askInput.trim()), 180);
    return () => window.clearTimeout(t);
  }, [askInput]);

  return (
    <div>
      {/* ----- LLM-driven search hero ----- */}
      <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-amber-50 via-white to-rose-50 px-6 py-5 mb-6 shadow-sm">
        <div className="flex items-baseline justify-between gap-3 mb-2">
          <label className="text-xs font-medium uppercase tracking-wide text-slate-600">
            Ask Hotpot
          </label>
          <span className="text-[11px] text-slate-500">
            an LLM agent reads your query and builds the search for you
          </span>
        </div>

        <div ref={inputWrapRef} className="relative flex flex-wrap items-center gap-2">
          <input
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
            placeholder="describe what you want — e.g. ‘ML papers from arxiv this year’"
            className="flex-1 min-w-[260px] border border-slate-300 rounded-lg px-3 py-2.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand-amber"
            autoFocus
          />
          <button
            type="button"
            onClick={() => runAsk()}
            disabled={!askInput.trim() || ask.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-dark text-white
                       px-4 py-2.5 text-sm font-medium hover:bg-black disabled:opacity-50
                       disabled:cursor-not-allowed transition-colors"
          >
            <span aria-hidden="true">✨</span>
            <span>{ask.isPending ? "Thinking…" : "Ask"}</span>
          </button>

          {historyOpen && suggestions.data && suggestions.data.length > 0 && (
            <div
              className="absolute z-30 left-0 right-0 top-[calc(100%+4px)]
                         max-h-72 overflow-y-auto rounded-lg border border-slate-200
                         bg-white shadow-lg text-sm"
            >
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wide
                              text-slate-500 border-b border-slate-100 flex items-center justify-between">
                <span>suggestions</span>
                <span className="opacity-70">esc to close</span>
              </div>
              {suggestions.data
                .slice(0, 12)
                .map((s) => (
                  <button
                    key={s.type + s.query}
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      runAsk(s.query);
                    }}
                    className="flex w-full items-center gap-2 text-left px-3 py-1.5 hover:bg-slate-50
                               border-b border-slate-50 last:border-0"
                  >
                    <span className="w-20 shrink-0 text-[10px] uppercase tracking-wide text-slate-400">
                      {formatSuggestionType(s.type)}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-slate-800">{s.label}</span>
                    <span className="max-w-[38%] truncate text-xs text-slate-400">
                      {s.detail ?? s.query}
                    </span>
                  </button>
                ))}
            </div>
          )}
        </div>
        <p className="mt-2 text-[11px] text-slate-600 leading-relaxed">
          <span className="inline-flex items-center gap-1 mr-1 px-1.5 py-0.5
                           rounded bg-amber-100 text-amber-900 font-bold not-italic">
            <span aria-hidden="true">⚠</span> Heads up
          </span>
          {consent === "accepted" ? (
            <>
              your queries are saved server-side (table{" "}
              <code className="font-mono bg-slate-100 px-1 rounded">search_logs</code>
              ) so the agent can be improved. Recent queries can appear in
              suggestions.{" "}
              <button
                type="button"
                onClick={() => setConsent("rejected")}
                className="underline underline-offset-2 hover:text-slate-900"
              >
                opt out
              </button>
            </>
          ) : consent === "rejected" ? (
            <>
              search-logging is <strong>off</strong> — your queries stay in
              your browser only. Source, topic, and title suggestions still
              work.{" "}
              <button
                type="button"
                onClick={() => setConsent("accepted")}
                className="underline underline-offset-2 hover:text-slate-900"
              >
                opt in
              </button>
            </>
          ) : (
            <>
              answer the consent banner first to choose whether your queries
              are recorded server-side. The agent works either way.
            </>
          )}
        </p>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <span className="text-xs text-slate-500 mr-1">try:</span>
          {TIPS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => runAsk(t)}
              className="text-xs px-2 py-0.5 rounded-full bg-white border border-slate-200
                         text-slate-700 hover:border-brand-amber hover:text-brand-dark"
            >
              {t}
            </button>
          ))}
        </div>

        {askError && <p className="mt-3 text-xs text-red-600">⚠ {askError}</p>}
        {explanation && (
          <p className="mt-3 text-xs text-slate-600">
            <span className="text-slate-400">▸</span> {explanation}
          </p>
        )}
      </div>

      {/* ----- Active filter chips (set by the LLM, removable) ----- */}
      {activeChips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-5">
          <span className="text-xs text-slate-500">filters:</span>
          {activeChips.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => removeFilter(k)}
              className="group inline-flex items-center gap-1 rounded-full border border-amber-300
                         bg-amber-50 px-2.5 py-1 text-xs text-amber-900 hover:bg-amber-100"
              title="click to remove"
            >
              <span className="opacity-70">{FILTER_LABELS[k]}:</span>
              <span className="font-medium">{String(filters[k])}</span>
              <span className="ml-0.5 opacity-50 group-hover:opacity-100">×</span>
            </button>
          ))}
          <button
            type="button"
            onClick={clearAll}
            className="text-xs text-slate-500 hover:text-slate-800 underline underline-offset-2 ml-1"
          >
            clear
          </button>
        </div>
      )}

      {showHot && (
        <HotNewsGrid
          hotItems={hotItems.data ?? []}
          isLoading={hotItems.isLoading}
        />
      )}

      {items.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {items.error && (
        <p className="text-sm text-red-600">
          Failed to load items. Is the backend reachable?
        </p>
      )}

      {items.data && (
        <>
          <p className="text-xs text-slate-500 mb-4">
            {items.data.total} item{items.data.total === 1 ? "" : "s"} · showing{" "}
            {items.data.items.length}
          </p>
          <div className="grid gap-4">
            {items.data.items.map((it) => (
              <ItemCard key={it.id} item={it} />
            ))}
          </div>
          {items.data.items.length === 0 && (
            <p className="text-sm text-slate-500 mt-8">
              No items match these filters. Remove a chip or ask something different.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function HotNewsGrid({
  hotItems,
  isLoading,
}: {
  hotItems: HotItem[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <p className="text-sm text-slate-500">Loading hot repeated stories…</p>
      </section>
    );
  }
  if (hotItems.length === 0) return null;

  return (
    <section className="mb-6 rounded-2xl border border-slate-200 bg-slate-950 p-5 text-white shadow-sm">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-300">
            hot news
          </p>
          <h2 className="font-serif text-2xl font-bold leading-tight">
            20 stories with repeat exposure and quality signal
          </h2>
        </div>
        <p className="max-w-xl text-xs leading-relaxed text-slate-300">
          Boosted when independent sources cover the same topic, then balanced
          with LLM quality, freshness, source trust, and clicks.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {hotItems.slice(0, 20).map((hot, index) => {
          const item = hot.item;
          const dateStr = (item.published_at ?? item.fetched_at).slice(0, 10);
          const excerpt = item.summary ?? item.excerpt;
          return (
            <article
              key={item.id}
              className="rounded-xl border border-white/10 bg-white/[0.06] p-4
                         transition hover:-translate-y-0.5 hover:border-emerald-300/50
                         hover:bg-white/[0.09]"
            >
              <div className="mb-2 flex items-center gap-2 text-[11px] text-slate-300">
                <span className="rounded-full bg-emerald-300 px-2 py-0.5 font-bold text-slate-950">
                  #{index + 1}
                </span>
                <span>{hot.source_count} source{hot.source_count === 1 ? "" : "s"}</span>
                <span>·</span>
                <span>{hot.support_count} exposure{hot.support_count === 1 ? "" : "s"}</span>
                <span className="ml-auto tabular-nums text-emerald-200">
                  {hot.hot_score.toFixed(2)}
                </span>
              </div>

              <h3 className="line-clamp-2 font-serif text-base font-bold leading-snug">
                <a
                  href={item.canonical_url}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-emerald-200"
                  onClick={() => bumpItemClick(item.id)}
                  onAuxClick={(e) => {
                    if (e.button === 1) bumpItemClick(item.id);
                  }}
                >
                  {item.title}
                </a>
              </h3>

              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                <span>{dateStr}</span>
                {hot.topic && (
                  <>
                    <span>·</span>
                    <span className="truncate">{hot.topic}</span>
                  </>
                )}
              </div>

              {excerpt && (
                <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-slate-300">
                  {excerpt}
                </p>
              )}

              {hot.sources.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {hot.sources.slice(0, 4).map((source) => (
                    <span
                      key={source}
                      className="max-w-full truncate rounded-full border border-white/10
                                 bg-white/[0.06] px-2 py-0.5 text-[10px] text-slate-300"
                    >
                      {source}
                    </span>
                  ))}
                  {hot.sources.length > 4 && (
                    <span className="rounded-full px-2 py-0.5 text-[10px] text-slate-400">
                      +{hot.sources.length - 4}
                    </span>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function describeFilters(f: Filters): string {
  const parts: string[] = [];
  if (f.topic) parts.push(`topic = ${f.topic}`);
  if (f.content_type) parts.push(`type = ${f.content_type}`);
  if (f.source) parts.push(`source ~ ${f.source}`);
  if (f.year) parts.push(`year = ${f.year}`);
  if (f.q) parts.push(`matches ~ ${f.q}`);
  if (f.sort && f.sort !== "smart") parts.push(`sort = ${f.sort}`);
  return parts.join(" · ");
}

function formatSuggestionType(type: string): string {
  if (type === "recent_query") return "recent";
  return type.replace("_", " ");
}
