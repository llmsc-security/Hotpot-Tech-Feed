import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { listItems, nlSearch, recentSearches, type NLFilter } from "../api";
import ItemCard from "../components/ItemCard";
import { useConsent } from "../hooks/useConsent";

const TIPS = [
  "ML papers from arxiv this year",
  "openai 2025 blog posts, newest first",
  "wechat: large model news",
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

const DEFAULT_FILTERS: Filters = { sort: "date_desc" };

export default function Browse() {
  const [askInput, setAskInput] = useState<string>("");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [askError, setAskError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const inputWrapRef = useRef<HTMLDivElement | null>(null);
  const qc = useQueryClient();
  const { consent, set: setConsent } = useConsent();

  const history = useQuery({
    queryKey: ["recent-searches"],
    queryFn: () => recentSearches(20),
    staleTime: 30_000,
    // Only fetch the recall list once the user has accepted logging.
    enabled: consent === "accepted",
  });

  const params = {
    limit: 50,
    offset: 0,
    topic: filters.topic ? `topic:${filters.topic}` : undefined,
    content_type: filters.content_type,
    source: filters.source,
    year: filters.year,
    q: filters.q,
    sort: filters.sort ?? "date_desc",
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
      // sort defaults to date_desc when the user didn't specify.
      const next: Filters = { sort: parsed.sort ?? "date_desc", ...parsed };
      if (!parsed.sort) next.sort = "date_desc";
      setFilters(next);
      const summary = describeFilters(next);
      setExplanation(summary || "no filters extracted — showing everything");
      // The backend just logged this query — refresh the recall list.
      qc.invalidateQueries({ queryKey: ["recent-searches"] });
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
    if (key === "sort") next.sort = "date_desc";
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
                   !(k === "sort" && filters.sort === "date_desc"));

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
            onChange={(e) => setAskInput(e.target.value)}
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

          {historyOpen && history.data && history.data.length > 0 && (
            <div
              className="absolute z-30 left-0 right-0 top-[calc(100%+4px)]
                         max-h-72 overflow-y-auto rounded-lg border border-slate-200
                         bg-white shadow-lg text-sm"
            >
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wide
                              text-slate-500 border-b border-slate-100 flex items-center justify-between">
                <span>recent queries</span>
                <span className="opacity-70">esc to close</span>
              </div>
              {history.data
                .filter((h) =>
                  askInput.trim()
                    ? h.query.toLowerCase().includes(askInput.toLowerCase())
                    : true
                )
                .slice(0, 12)
                .map((h) => (
                  <button
                    key={h.query + h.last_used_at}
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      runAsk(h.query);
                    }}
                    className="block w-full text-left px-3 py-1.5 hover:bg-slate-50
                               border-b border-slate-50 last:border-0"
                  >
                    <span className="text-slate-800">{h.query}</span>
                    <span className="float-right text-xs text-slate-400">
                      {formatRelative(h.last_used_at)}
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
              ) so the agent can be improved. The recall list above is a
              shortcut: click any entry to re-run it.{" "}
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
              your browser only and the recall list is disabled. The agent
              still works.{" "}
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

function describeFilters(f: Filters): string {
  const parts: string[] = [];
  if (f.topic) parts.push(`topic = ${f.topic}`);
  if (f.content_type) parts.push(`type = ${f.content_type}`);
  if (f.source) parts.push(`source ~ ${f.source}`);
  if (f.year) parts.push(`year = ${f.year}`);
  if (f.q) parts.push(`title ~ ${f.q}`);
  if (f.sort && f.sort !== "date_desc") parts.push(`sort = ${f.sort}`);
  return parts.join(" · ");
}

function formatRelative(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  if (Number.isNaN(t)) return "";
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(t).toISOString().slice(0, 10);
}
