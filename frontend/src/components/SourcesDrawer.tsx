import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { listSources, type SourceSummary } from "../api";

export default function SourcesDrawer({ onClose }: { onClose: () => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["sources-drawer"],
    queryFn: listSources,
    staleTime: 60_000,
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40"
      onClick={onClose}
    >
      <aside
        className="w-full max-w-md h-full bg-white shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between px-5 py-4 border-b border-slate-200">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Sources</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {data
                ? `${data.total} source${data.total === 1 ? "" : "s"} feeding the corpus`
                : "loading…"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 text-2xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          {isLoading && <p className="text-sm text-slate-500 px-3 py-4">Loading…</p>}
          {error && (
            <p className="text-sm text-red-600 px-3 py-4">
              Failed to load sources.
            </p>
          )}
          {data?.sources?.map((s) => (
            <SourceRow key={s.id} s={s} />
          ))}
        </div>
      </aside>
    </div>
  );
}

const HEALTH_COLOR: Record<SourceSummary["health_status"], string> = {
  ok: "bg-emerald-500",
  degraded: "bg-amber-500",
  broken: "bg-red-500",
  unknown: "bg-slate-300",
};

function SourceRow({ s }: { s: SourceSummary }) {
  const isInternal = s.url.startsWith("user-contributions://");
  return (
    <div className="px-3 py-2.5 rounded-lg hover:bg-slate-50">
      <div className="flex items-baseline gap-2">
        <span
          className={`inline-block w-1.5 h-1.5 rounded-full mt-1.5 ${HEALTH_COLOR[s.health_status]}`}
          title={`health: ${s.health_status}`}
        />
        <span className="font-medium text-sm text-slate-900 flex-1">{s.name}</span>
        <span className="text-xs text-slate-500 tabular-nums">
          {s.item_count.toLocaleString()}
        </span>
      </div>
      <div className="ml-3.5 mt-0.5 flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wide text-slate-400">
          {s.kind}
        </span>
        {isInternal ? (
          <span className="text-xs text-slate-500 italic truncate">
            user contributions
          </span>
        ) : (
          <a
            href={s.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline truncate"
            title={s.url}
          >
            {s.url}
          </a>
        )}
      </div>
    </div>
  );
}
