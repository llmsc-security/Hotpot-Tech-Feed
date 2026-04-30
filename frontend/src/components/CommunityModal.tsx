import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { listCommunity, type CommunitySort } from "../api";
import ContributePanel from "./ContributePanel";
import ItemCard from "./ItemCard";

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 30) return `${d}d ago`;
  const mo = Math.round(d / 30);
  return `${mo}mo ago`;
}

export default function CommunityModal({ onClose }: { onClose: () => void }) {
  const [sort, setSort] = useState<CommunitySort>("hot");
  const { data, isLoading, error } = useQuery({
    queryKey: ["community", sort],
    queryFn: () => listCommunity({ sort, limit: 100 }),
    staleTime: 30_000,
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
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 py-6 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-2xl bg-white shadow-xl border border-slate-200 my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between px-6 pt-5 pb-3 border-b border-slate-100">
          <div>
            <h2 className="font-serif text-xl font-bold text-slate-900">
              🔥 Community
            </h2>
            <p className="text-xs text-slate-500 mt-0.5 max-w-md">
              Share a URL — auto-accepted, no curation gate. Below, every
              contribution ranked by clicks: the more people open it from the
              feed, the hotter it gets.
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

        <div className="px-6 py-4 space-y-4">
          <ContributePanel />

          <div className="flex items-center gap-2 pt-1">
            <SortChip
              label="🔥 Hot"
              active={sort === "hot"}
              onClick={() => setSort("hot")}
            />
            <SortChip
              label="🆕 Recently added"
              active={sort === "recent"}
              onClick={() => setSort("recent")}
            />
            <span className="ml-auto text-xs text-slate-500 tabular-nums">
              {data
                ? `${data.total} contribution${data.total === 1 ? "" : "s"}`
                : "…"}
            </span>
          </div>

          {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {error && (
            <p className="text-sm text-red-600">Failed to load community feed.</p>
          )}

          {data && data.items.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-8 text-center">
              <p className="text-sm text-slate-700 font-medium">
                No community contributions yet.
              </p>
              <p className="text-xs text-slate-500 mt-1">
                Be the first — paste a URL above.
              </p>
            </div>
          )}

          <ul className="space-y-3 max-h-[55vh] overflow-y-auto pr-1">
            {data?.items.map((it) => (
              <li key={it.id}>
                <div className="flex items-baseline gap-2 mb-1 px-1">
                  <span
                    className="text-[10px] uppercase tracking-wide text-slate-400"
                    title={`contributed ${new Date(it.fetched_at).toLocaleString()}`}
                  >
                    {relativeTime(it.fetched_at)}
                  </span>
                </div>
                <ItemCard item={it} />
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function SortChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
        active
          ? "bg-brand-amber text-brand-dark border-amber-300"
          : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
      }`}
    >
      {label}
    </button>
  );
}
