import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { bumpItemClick, getSecurityStats, listSecurityHot, listSecurityItems } from "../api";
import { ExternalIcon, FlameIcon, ShieldIcon, SparklesIcon } from "../components/HotpotIcons";
import type {
  SecurityItem,
  SecuritySection,
  SecuritySoftArticle,
  SecuritySort,
  SecurityStats,
} from "../types";

const PAGE_SIZE = 25;

const SECTIONS: { key: SecuritySection; label: string }[] = [
  { key: "all", label: "All" },
  { key: "exploited_now", label: "Exploited" },
  { key: "new_important_cves", label: "CVEs" },
  { key: "real_attack_cases", label: "Attack cases" },
  { key: "technical_analysis", label: "Technical" },
  { key: "vendor_advisories", label: "Vendor" },
  { key: "oss_package_vulnerabilities", label: "OSS" },
];

const SORTS: { key: SecuritySort; label: string }[] = [
  { key: "score_desc", label: "Score" },
  { key: "hot_desc", label: "Hot" },
  { key: "date_desc", label: "Newest" },
];

export default function Security() {
  const [section, setSection] = useState<SecuritySection>("all");
  const [sort, setSort] = useState<SecuritySort>("score_desc");
  const [page, setPage] = useState(0);

  const hot = useQuery({
    queryKey: ["security-hot", 10],
    queryFn: () => listSecurityHot({ limit: 10 }),
    staleTime: 60_000,
  });

  const feed = useQuery({
    queryKey: ["security-items", section, sort, page],
    queryFn: () =>
      listSecurityItems({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        section,
        sort,
      }),
    staleTime: 60_000,
  });

  const stats = useQuery({
    queryKey: ["security-stats"],
    queryFn: getSecurityStats,
    staleTime: 60_000,
  });

  const total = feed.data?.total ?? 0;
  const start = page * PAGE_SIZE + 1;
  const end = Math.min((page + 1) * PAGE_SIZE, total);
  const canPrev = page > 0;
  const canNext = !!feed.data && end < total;

  return (
    <div className="gx-page-stack">
      <div className="gx-page-title">
        <div className="min-w-0">
          <div className="gx-title-row">
            <ShieldIcon size={20} className="text-[var(--gx-chili)]" />
            <h1>Security pulse</h1>
          </div>
          <p>Evidence-ranked security feed with source chains, exploit signal, and actionability.</p>
        </div>
        <div className="grid w-full grid-cols-2 gap-2 sm:w-auto sm:grid-cols-4">
          <div className="gx-stat gx-stat-alert">
            <strong>{hot.data?.length ?? "..."}</strong>
            <span>hot groups</span>
          </div>
          <div className="gx-stat">
            <strong>{stats.data?.accepted.toLocaleString() ?? "..."}</strong>
            <span>accepted</span>
          </div>
          <div className="gx-stat">
            <strong>{stats.data?.rejected.toLocaleString() ?? "..."}</strong>
            <span>filtered</span>
          </div>
          <div className="gx-stat">
            <strong>
              {stats.data ? `${Math.round(stats.data.accept_rate * 1000) / 10}%` : "..."}
            </strong>
            <span>accept rate</span>
          </div>
        </div>
      </div>

      <section className="gx-card p-4 shadow-sm sm:p-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-[var(--gx-chili)]">
              <FlameIcon size={13} />
              security hot 10
            </p>
            <h2 className="gx-section-title text-xl font-bold leading-tight text-[var(--gx-ink)] sm:text-2xl">
              High-score stories ranked by evidence and corroboration
            </h2>
          </div>
          {hot.data && hot.data.length > 0 && (
            <div className="text-right text-xs text-[var(--gx-muted)]">
              {hot.data.length} story group{hot.data.length === 1 ? "" : "s"}
            </div>
          )}
        </div>

        {hot.isLoading && <p className="text-sm text-[var(--gx-muted)]">Loading...</p>}
        {hot.error && <p className="text-sm text-red-700">Security hot feed is unavailable.</p>}
        {hot.data && hot.data.length === 0 && (
          <p className="text-sm text-[var(--gx-muted)]">
            No hot security groups have passed the current score threshold.
          </p>
        )}
        {hot.data && hot.data.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {hot.data.map((story, index) => (
              <SecurityHotCard key={story.security.group_key} story={story} rank={index + 1} />
            ))}
          </div>
        )}
      </section>

      <section className="gx-card p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[var(--gx-muted)]">
              security feed
            </p>
            <h2 className="gx-section-title text-xl font-bold text-[var(--gx-ink)] sm:text-2xl">
              Accepted security groups
            </h2>
          </div>
          <label className="flex items-center gap-2 text-xs text-[var(--gx-muted)]">
            <span>Sort</span>
            <select
              value={sort}
              onChange={(e) => {
                setSort(e.target.value as SecuritySort);
                setPage(0);
              }}
              className="rounded-md border border-[var(--gx-line)] bg-white px-2 py-1.5 text-sm text-[var(--gx-ink)]
                         outline-none focus:border-[var(--gx-chili)] focus:ring-4 focus:ring-[rgba(200,68,44,0.10)]"
            >
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mb-4 flex gap-2 overflow-x-auto pb-1 sm:flex-wrap sm:overflow-visible sm:pb-0">
          {SECTIONS.map((s) => {
            const active = s.key === section;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => {
                  setSection(s.key);
                  setPage(0);
                }}
                className={`gx-chip shrink-0 ${active ? "gx-chip-dark" : ""}`}
              >
                {s.label}
              </button>
            );
          })}
        </div>

        {feed.isLoading && <p className="text-sm text-[var(--gx-muted)]">Loading...</p>}
        {feed.error && (
          <p className="text-sm text-red-700">
            Failed to load the security feed. Is the backend reachable?
          </p>
        )}

        {feed.data && (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-xs text-[var(--gx-muted)]">
              <span>{total === 0 ? "0 groups" : `${start}-${end} of ${total} groups`}</span>
              <span>score version {feed.data.items[0]?.security.score_version ?? "security-v1"}</span>
            </div>

            <div className="grid gap-3">
              {feed.data.items.map((story) => (
                <SecurityStoryRow key={story.security.group_key} story={story} />
              ))}
            </div>

            {feed.data.items.length === 0 && (
              <p className="mt-8 text-sm text-[var(--gx-muted)]">
                No accepted security groups in this section.
              </p>
            )}

            <div className="mt-5 flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={!canPrev}
                className="gx-btn disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-xs text-[var(--gx-muted)]">Page {page + 1}</span>
              <button
                type="button"
                onClick={() => setPage((p) => p + 1)}
                disabled={!canNext}
                className="gx-btn disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </>
        )}
      </section>

      <SecurityTechCard stats={stats.data} isLoading={stats.isLoading} />
    </div>
  );
}

function SecurityHotCard({ story, rank }: { story: SecurityItem; rank: number }) {
  const { security } = story;
  return (
    <article
      className="relative flex min-w-0 flex-col rounded-xl border border-[var(--gx-line)]
                 bg-white p-3 shadow-sm transition hover:-translate-y-0.5
                 hover:border-[var(--gx-chili)] hover:shadow-md"
    >
      <div className="absolute inset-x-0 top-0 h-1 rounded-t-xl bg-[var(--gx-chili)]" />
      <div className="mb-3 mt-1 flex flex-wrap items-center gap-2 text-[11px] text-[var(--gx-muted)]">
        <span className="rounded bg-[var(--gx-chili)] px-2 py-0.5 font-bold text-white">
          #{rank}
        </span>
        <SourceCount story={story} />
        <span className="ml-auto rounded bg-[var(--gx-chili-soft)] px-2 py-0.5 font-mono font-bold tabular-nums text-[var(--gx-chili)]">
          hot {score(security.security_hot_score)}
        </span>
      </div>
      <h3 className="gx-section-title line-clamp-3 text-base font-bold leading-snug text-[var(--gx-ink)]">
        <SecurityLink story={story} className="hover:text-[var(--gx-chili)]" />
      </h3>
      <BadgeList badges={security.badges} />
      <WhyList reasons={security.why_ranked} limit={2} />
    </article>
  );
}

function SecurityStoryRow({ story }: { story: SecurityItem }) {
  const { item, security } = story;
  const excerpt = item.summary ?? item.excerpt;
  return (
    <article className="gx-security-card min-w-0 rounded-xl p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-[var(--gx-muted)]">
        <span className="gx-chip gx-chip-dark px-2 py-0.5 text-[10px] uppercase tracking-wide">
          {sectionLabel(security.section)}
        </span>
        {item.source_name && <span className="max-w-[180px] truncate">{item.source_name}</span>}
        <span>{dateText(security.event_time ?? item.published_at ?? item.fetched_at)}</span>
        <SourceCount story={story} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_250px]">
        <div className="min-w-0">
          <h3 className="gx-section-title text-base font-bold leading-snug text-[var(--gx-ink)] sm:text-lg">
            <SecurityLink story={story} className="hover:text-[var(--gx-chili)]" />
          </h3>
          {excerpt && (
            <p className="mt-2 text-sm leading-relaxed text-[var(--gx-ink-2)]">{excerpt}</p>
          )}
          <BadgeList badges={security.badges} />
          <WhyList reasons={security.why_ranked} />
        </div>

        <div className="grid content-start gap-3 text-xs">
          <ScoreBar
            label="Final"
            value={security.final_security_score}
            tooltip={scoreEvidence(story, "final")}
            strong
          />
          <ScoreBar
            label="Evidence"
            value={security.evidence_score}
            tooltip={scoreEvidence(story, "evidence")}
          />
          <ScoreBar
            label="Exploit"
            value={security.exploitation_score}
            tooltip={scoreEvidence(story, "exploit")}
          />
          <ScoreBar
            label="Action"
            value={security.actionability_score}
            tooltip={scoreEvidence(story, "action")}
          />
        </div>
      </div>
    </article>
  );
}

function SecurityLink({ story, className = "" }: { story: SecurityItem; className?: string }) {
  return (
    <a
      href={story.item.canonical_url}
      target="_blank"
      rel="noreferrer"
      className={className}
      onClick={() => bumpItemClick(story.item.id)}
      onAuxClick={(e) => {
        if (e.button === 1) bumpItemClick(story.item.id);
      }}
    >
      {story.item.title}
    </a>
  );
}

function SourceCount({ story, dark = false }: { story: SecurityItem; dark?: boolean }) {
  const title = sourceTitle(story);
  const plural = story.source_count === 1 ? "source" : "sources";
  return (
    <span
      tabIndex={0}
      className={`group relative inline-flex outline-none ${
        dark
          ? "rounded border border-white/10 bg-white/[0.06] px-1.5 py-0.5 text-stone-300"
          : "gx-chip gx-chip-emerald px-2 py-0.5 text-[11px]"
      }`}
      title={title}
      aria-label={title}
    >
      {story.source_count} {plural}
      <span
        className={`pointer-events-none absolute left-0 top-[calc(100%+6px)] z-30 hidden w-72 max-w-[calc(100vw-2rem)]
                    rounded-md border px-3 py-2 text-left text-[11px] leading-relaxed shadow-lg
                    group-hover:block group-focus:block ${
                      dark
                        ? "border-white/10 bg-stone-950 text-stone-100"
                        : "border-[var(--gx-line)] bg-white text-[var(--gx-ink-2)]"
                    }`}
      >
        {title}
      </span>
    </span>
  );
}

function ScoreBar({
  label,
  value,
  tooltip,
  strong = false,
}: {
  label: string;
  value: number;
  tooltip: string;
  strong?: boolean;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="group relative outline-none" title={tooltip} aria-label={tooltip} tabIndex={0}>
      <div className="gx-score-row">
        <span className="gx-score-label underline decoration-dotted underline-offset-4">
          {label}
        </span>
        <div className="gx-score-track">
          <div
            className={`gx-score-fill ${strong ? "" : "bg-[var(--gx-ink)]"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className={`gx-score-num ${strong ? "text-[var(--gx-chili)]" : ""}`}>
          {score(value)}
        </span>
      </div>
      <div
        className="pointer-events-none absolute bottom-[calc(100%+6px)] right-0 z-30 hidden w-80 max-w-[calc(100vw-2rem)]
                   rounded-md border border-[var(--gx-line)] bg-white px-3 py-2 text-[11px] leading-relaxed
                   text-[var(--gx-ink-2)] shadow-lg group-hover:block group-focus:block"
      >
        {tooltip}
      </div>
    </div>
  );
}

function BadgeList({ badges, dark = false }: { badges: string[]; dark?: boolean }) {
  if (badges.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {badges.slice(0, 7).map((badge) => (
        <span
          key={badge}
          className={
            dark
              ? "max-w-full truncate rounded border border-white/10 bg-white/[0.08] px-2 py-0.5 text-[11px] text-stone-200"
              : "gx-chip px-2 py-0.5 text-[11px]"
          }
        >
          {badge}
        </span>
      ))}
    </div>
  );
}

function WhyList({
  reasons,
  dark = false,
  limit = 4,
}: {
  reasons: string[];
  dark?: boolean;
  limit?: number;
}) {
  if (reasons.length === 0) return null;
  return (
    <div className={`mt-3 flex flex-wrap gap-1.5 text-[11px] ${dark ? "text-stone-300" : "text-[var(--gx-muted)]"}`}>
      {reasons.slice(0, limit).map((reason) => (
        <span key={reason}>{reason}</span>
      ))}
    </div>
  );
}

function SecurityTechCard({
  stats,
  isLoading,
}: {
  stats: SecurityStats | undefined;
  isLoading: boolean;
}) {
  const [open, setOpen] = useState(false);
  const maxReject = Math.max(...(stats?.reject_reasons.map((b) => b.count) ?? [1]), 1);
  const maxScoreBucket = Math.max(...(stats?.score_distribution.map((b) => b.count) ?? [1]), 1);

  return (
    <section className="gx-card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-4 text-left sm:px-5"
        aria-expanded={open}
      >
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-[var(--gx-muted)]">
            <SparklesIcon size={13} />
            technical diagnostics
          </p>
          <h2 className="gx-section-title text-lg font-bold text-[var(--gx-ink)] sm:text-xl">
            Score, rank, filter-out dataflow
          </h2>
        </div>
        <span className="gx-chip shrink-0">{open ? "Collapse" : "Expand"}</span>
      </button>

      {open && (
        <div className="border-t border-[var(--gx-line-2)] px-4 pb-5 sm:px-5">
          {isLoading && <p className="pt-4 text-sm text-[var(--gx-muted)]">Loading diagnostics...</p>}
          {!isLoading && !stats && (
            <p className="pt-4 text-sm text-red-700">Security diagnostics are unavailable.</p>
          )}
          {stats && (
            <div className="space-y-5 pt-4">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard label="Total processed" value={stats.total_scored} />
                <MetricCard label="Accepted" value={stats.accepted} />
                <MetricCard label="Filtered out" value={stats.rejected} />
                <MetricCard label="Accept rate" value={`${Math.round(stats.accept_rate * 1000) / 10}%`} />
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-sm font-bold text-[var(--gx-ink)]">Filter-out reasons</h3>
                  <div className="space-y-2">
                    {stats.reject_reasons.map((bucket) => (
                      <BarRow
                        key={bucket.key}
                        label={reasonLabel(bucket.key)}
                        count={bucket.count}
                        max={maxReject}
                        tone="red"
                      />
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="mb-2 text-sm font-bold text-[var(--gx-ink)]">Final score distribution</h3>
                  <div className="space-y-2">
                    {stats.score_distribution.map((bucket) => (
                      <BarRow
                        key={bucket.bucket}
                        label={bucket.bucket}
                        count={bucket.count}
                        max={maxScoreBucket}
                        tone="slate"
                      />
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-bold text-[var(--gx-ink)]">Accepted section mix</h3>
                <div className="flex flex-wrap gap-2">
                  {stats.sections.map((bucket) => (
                    <span key={bucket.key} className="gx-chip">
                      {sectionLabel(bucket.key as SecuritySection)} - {bucket.count}
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-bold text-[var(--gx-ink)]">软文过滤高分样本</h3>
                <div className="grid gap-2">
                  {stats.soft_article_top.slice(0, 8).map((entry) => (
                    <SoftArticleRow key={entry.item.id} entry={entry} />
                  ))}
                </div>
              </div>

              <p className="text-xs text-[var(--gx-muted)]">
                Score version {stats.score_version}. Pagination and hot ranking use the persisted
                security score projection, not generic Item.score.
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function MetricCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-[var(--gx-line)] bg-[var(--gx-surface-2)] px-3 py-3">
      <p className="text-[11px] uppercase tracking-wide text-[var(--gx-muted)]">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--gx-ink)]">
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
    </div>
  );
}

function BarRow({
  label,
  count,
  max,
  tone,
}: {
  label: string;
  count: number;
  max: number;
  tone: "red" | "slate";
}) {
  const pct = Math.max(3, Math.round((count / max) * 100));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
        <span className="truncate text-[var(--gx-ink-2)]">{label}</span>
        <span className="tabular-nums text-[var(--gx-muted)]">{count.toLocaleString()}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-[var(--gx-line-2)]">
        <div
          className={`h-full rounded-full ${tone === "red" ? "bg-[var(--gx-chili)]" : "bg-[var(--gx-ink)]"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function SoftArticleRow({ entry }: { entry: SecuritySoftArticle }) {
  return (
    <article className="rounded-lg border border-[var(--gx-line)] px-3 py-3">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--gx-muted)]">
        <span className="gx-chip gx-chip-chili px-2 py-0.5">
          软文 {score(entry.soft_article_score)}
        </span>
        <span>evidence {score(entry.evidence_score)}</span>
        <span>final {score(entry.final_security_score)}</span>
        {entry.reject_reason && <span>{reasonLabel(entry.reject_reason)}</span>}
      </div>
      <h4 className="gx-section-title mt-1 line-clamp-2 text-sm font-semibold text-[var(--gx-ink)]">
        <a
          href={entry.item.canonical_url}
          target="_blank"
          rel="noreferrer"
          className="hover:text-[var(--gx-chili)]"
          onClick={() => bumpItemClick(entry.item.id)}
        >
          {entry.item.title}
        </a>
      </h4>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {entry.badges.slice(0, 4).map((badge) => (
          <span key={badge} className="gx-chip px-2 py-0.5 text-[11px]">
            {badge}
          </span>
        ))}
      </div>
    </article>
  );
}

function score(value: number): string {
  return value.toFixed(2);
}

function dateText(value: string | null): string {
  if (!value) return "unknown date";
  return value.slice(0, 10);
}

function sectionLabel(section: SecuritySection): string {
  return SECTIONS.find((s) => s.key === section)?.label ?? section.replaceAll("_", " ");
}

function reasonLabel(reason: string): string {
  if (reason === "soft_article") return "软文/营销过滤";
  return reason.replaceAll("_", " ");
}

function sourceTitle(story: SecurityItem): string {
  if (story.sources.length === 0) return "Source: unknown";
  return `Sources: ${story.sources.join(", ")}`;
}

function scoreEvidence(story: SecurityItem, kind: "final" | "evidence" | "exploit" | "action"): string {
  const security = story.security;
  const badges = security.badges.length ? security.badges.join(", ") : "none";
  const reasons = security.why_ranked.length ? security.why_ranked.join("; ") : "no extracted reason";
  const chain = security.source_chain.length ? security.source_chain.join(", ") : "article/source text only";

  if (kind === "final") {
    return [
      `Final ${score(security.final_security_score)} = weighted security score.`,
      `Evidence ${score(security.evidence_score)}, exploit ${score(security.exploitation_score)}, quality ${score(security.content_quality_score)}, impact ${score(security.impact_score)}, action ${score(security.actionability_score)}.`,
      `软文惩罚 ${score(security.soft_article_score)}.`,
      `Why: ${reasons}.`,
    ].join(" ");
  }
  if (kind === "evidence") {
    return [
      `Evidence ${score(security.evidence_score)} from concrete security signals.`,
      `Badges: ${badges}.`,
      `Source chain: ${chain}.`,
      `Why: ${reasons}.`,
    ].join(" ");
  }
  if (kind === "exploit") {
    return [
      `Exploit ${score(security.exploitation_score)} reflects KEV, confirmed exploitation, credible reports, or PoC signals.`,
      `Badges: ${badges}.`,
      `Why: ${reasons}.`,
    ].join(" ");
  }
  return [
    `Action ${score(security.actionability_score)} reflects patch, mitigation, detection, IoC, affected-version, or workaround detail.`,
    `Badges: ${badges}.`,
    `Why: ${reasons}.`,
  ].join(" ");
}
