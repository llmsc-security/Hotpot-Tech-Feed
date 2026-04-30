import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listCommunity, type CommunitySort } from "../api";
import ContributePanel from "../components/ContributePanel";
import ItemCard from "../components/ItemCard";

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

export default function Community() {
  const [sort, setSort] = useState<CommunitySort>("hot");
  const { data, isLoading, error } = useQuery({
    queryKey: ["community", sort],
    queryFn: () => listCommunity({ sort, limit: 100 }),
    staleTime: 30_000,
  });

  return (
    <div className="space-y-5">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-serif text-3xl font-bold text-slate-900">
            Community
          </h1>
          <p className="text-sm text-slate-600 mt-1 max-w-2xl">
            Share a URL and it lands in the feed instantly — auto-accepted, no
            curation gate. Below, every contribution ranked by click count:
            the more people open a link from the feed, the hotter it gets.
          </p>
        </div>
        <Link
          to="/"
          className="text-xs text-slate-500 hover:text-slate-900 underline underline-offset-2"
        >
          ← back to feed
        </Link>
      </header>

      <ContributePanel />

      <div className="flex items-center gap-2">
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
          {data ? `${data.total} contribution${data.total === 1 ? "" : "s"}` : "…"}
        </span>
      </div>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {error && (
        <p className="text-sm text-red-600">
          Failed to load community feed.
        </p>
      )}

      {data && data.items.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center">
          <p className="text-sm text-slate-700 font-medium">
            No community contributions yet.
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Be the first — click <strong>I want to contribute</strong> in the
            top right and paste a URL.
          </p>
        </div>
      )}

      <ul className="space-y-3">
        {data?.items.map((it) => (
          <li key={it.id} className="relative">
            <div className="absolute -left-3 top-3 hidden md:block">
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
