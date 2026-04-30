import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { listItems, nlSearch, type NLFilter } from "../api";
import ItemCard from "../components/ItemCard";

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
    mutationFn: nlSearch,
    onSuccess: (parsed) => {
      setAskError(null);
      // Each Ask is a full replacement: the LLM saw the whole user intent.
      // sort defaults to date_desc when the user didn't specify.
      const next: Filters = { sort: parsed.sort ?? "date_desc", ...parsed };
      if (!parsed.sort) next.sort = "date_desc";
      setFilters(next);
      const summary = describeFilters(next);
      setExplanation(summary || "no filters extracted — showing everything");
    },
    onError: (err: Error) => {
      setAskError(err.message);
      setExplanation(null);
    },
  });

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

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={askInput}
            onChange={(e) => setAskInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") runAsk();
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
        </div>

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
