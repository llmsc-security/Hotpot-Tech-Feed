import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listCandidates,
  listCategories,
  listContentTypes,
  listSources,
  promoteCandidate,
  rejectCandidate,
  type CategoryBucket,
  type ContentTypeBucket,
  type SourceCandidate,
  type SourceSummary,
} from "../api";

const CONTENT_TYPE_LABEL: Record<string, string> = {
  paper: "Papers",
  blog: "Blogs",
  news: "News",
  lab_announcement: "Lab announcements",
  tutorial: "Tutorials",
  oss_release: "OSS releases",
  other: "Other",
};

export default function SourcesDrawer({ onClose }: { onClose: () => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["sources-drawer"],
    queryFn: listSources,
    staleTime: 60_000,
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: listCategories,
    staleTime: 60_000,
  });
  const contentTypes = useQuery({
    queryKey: ["content-types"],
    queryFn: listContentTypes,
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

        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-3">
          <DiscoverySection />
          <CollectionCard
            title="Categories"
            subtitle="user-confirmed primary category"
            items={(categories.data ?? []).slice(0, 3).map((b: CategoryBucket) => ({
              label: b.category,
              count: b.count,
            }))}
            total={categories.data?.length ?? 0}
          />
          <CollectionCard
            title="Content types"
            subtitle="LLM-classified content_type"
            items={(contentTypes.data ?? []).slice(0, 3).map((b: ContentTypeBucket) => ({
              label: CONTENT_TYPE_LABEL[b.content_type] ?? b.content_type,
              count: b.count,
            }))}
            total={contentTypes.data?.length ?? 0}
          />

          <div>
            <p className="px-3 pt-1 pb-1.5 text-[10px] uppercase tracking-wide text-slate-500">
              Sources ({data?.total ?? "…"})
            </p>
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
        </div>
      </aside>
    </div>
  );
}

function CollectionCard({
  title,
  subtitle,
  items,
  total,
}: {
  title: string;
  subtitle: string;
  items: { label: string; count: number }[];
  total: number;
}) {
  const max = Math.max(1, ...items.map((i) => i.count));
  return (
    <div className="rounded-xl border border-slate-200 bg-gradient-to-br from-amber-50 via-white to-rose-50 px-3 py-2.5">
      <div className="flex items-baseline justify-between mb-1.5">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <p className="text-[10px] text-slate-500">{subtitle}</p>
        </div>
        <span className="text-[10px] text-slate-400 tabular-nums">
          top 3 of {total}
        </span>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-slate-500 italic">no data yet</p>
      ) : (
        <ul className="space-y-1">
          {items.map((b, i) => (
            <li key={b.label} className="flex items-center gap-2 text-xs">
              <span className="text-[10px] uppercase tracking-wide text-slate-400 w-5">
                #{i + 1}
              </span>
              <span className="font-medium text-slate-900 flex-1 truncate">
                {b.label}
              </span>
              <div className="w-20 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full bg-brand-amber"
                  style={{ width: `${(b.count / max) * 100}%` }}
                />
              </div>
              <span className="text-slate-500 tabular-nums w-12 text-right">
                {b.count.toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DiscoverySection() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["candidates", "pending"],
    queryFn: () => listCandidates("pending", 30),
    staleTime: 60_000,
  });

  const promote = useMutation({
    mutationFn: (id: string) => promoteCandidate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      qc.invalidateQueries({ queryKey: ["sources-drawer"] });
    },
  });
  const reject = useMutation({
    mutationFn: (id: string) => rejectCandidate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["candidates"] }),
  });

  const cands = data?.candidates ?? [];
  if (cands.length === 0) return null;

  return (
    <div className="rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50 via-white to-rose-50 px-3 py-2.5">
      <div className="flex items-baseline justify-between mb-1.5">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">
            🔍 Discovery ({data?.total ?? cands.length})
          </h3>
          <p className="text-[10px] text-slate-500">
            new sources spotted by the auto-job — click ✓ to add, ✗ to reject
          </p>
        </div>
      </div>
      <ul className="space-y-1.5">
        {cands.slice(0, 8).map((c: SourceCandidate) => (
          <li key={c.id} className="text-xs">
            <div className="flex items-center gap-1.5">
              {c.is_llm_focused && (
                <span
                  className="text-[9px] uppercase font-bold text-amber-800
                             bg-amber-100 px-1 py-0.5 rounded"
                  title="LLM-focused"
                >
                  LLM
                </span>
              )}
              {c.academic_depth === "high" && (
                <span
                  className="text-[9px] uppercase font-bold text-emerald-800
                             bg-emerald-100 px-1 py-0.5 rounded"
                  title="High academic depth"
                >
                  🎓
                </span>
              )}
              <a
                href={c.sample_url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-slate-900 truncate flex-1 hover:underline"
                title={c.sample_url}
              >
                {c.name_hint || c.domain}
              </a>
              <span className="text-[10px] text-slate-400 tabular-nums">
                {Math.round(c.signal_score * 100)}
              </span>
              <button
                type="button"
                disabled={promote.isPending}
                onClick={() => promote.mutate(c.id)}
                className="text-emerald-700 hover:text-emerald-900 px-1"
                title="Add as a tracked source"
              >
                ✓
              </button>
              <button
                type="button"
                disabled={reject.isPending}
                onClick={() => reject.mutate(c.id)}
                className="text-slate-400 hover:text-red-600 px-1"
                title="Reject"
              >
                ✗
              </button>
            </div>
            {c.llm_rationale && (
              <p className="text-[10px] text-slate-500 ml-1 line-clamp-1 italic">
                {c.llm_rationale}
              </p>
            )}
          </li>
        ))}
      </ul>
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
