import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { bumpItemClick, listSecurityHot, listSecurityItems } from "../api";
import type { SecurityItem, SecuritySection, SecuritySort } from "../types";

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

  const total = feed.data?.total ?? 0;
  const start = page * PAGE_SIZE + 1;
  const end = Math.min((page + 1) * PAGE_SIZE, total);
  const canPrev = page > 0;
  const canNext = !!feed.data && end < total;

  return (
    <div className="space-y-5 sm:space-y-7">
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-white shadow-sm sm:p-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand-amber">
              security hot 10
            </p>
            <h1 className="font-serif text-xl font-bold leading-tight sm:text-2xl">
              Evidence-ranked security stories
            </h1>
          </div>
          {hot.data && hot.data.length > 0 && (
            <div className="text-right text-xs text-slate-300">
              {hot.data.length} story group{hot.data.length === 1 ? "" : "s"}
            </div>
          )}
        </div>

        {hot.isLoading && <p className="text-sm text-slate-400">Loading...</p>}
        {hot.error && (
          <p className="text-sm text-red-300">Security hot feed is unavailable.</p>
        )}
        {hot.data && hot.data.length === 0 && (
          <p className="text-sm text-slate-400">
            No hot security groups have passed the current score threshold.
          </p>
        )}
        {hot.data && hot.data.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {hot.data.map((story, index) => (
              <SecurityHotCard key={story.security.group_key} story={story} rank={index + 1} />
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              security feed
            </p>
            <h2 className="font-serif text-xl font-bold text-slate-950 sm:text-2xl">
              Accepted security groups
            </h2>
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <span>Sort</span>
            <select
              value={sort}
              onChange={(e) => {
                setSort(e.target.value as SecuritySort);
                setPage(0);
              }}
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-800
                         focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand-tint"
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
                className={`shrink-0 rounded-md border px-3 py-1.5 text-sm transition ${
                  active
                    ? "border-brand bg-brand text-white"
                    : "border-slate-200 bg-white text-slate-700 hover:border-brand-amber"
                }`}
              >
                {s.label}
              </button>
            );
          })}
        </div>

        {feed.isLoading && <p className="text-sm text-slate-500">Loading...</p>}
        {feed.error && (
          <p className="text-sm text-red-600">
            Failed to load the security feed. Is the backend reachable?
          </p>
        )}

        {feed.data && (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
              <span>
                {total === 0 ? "0 groups" : `${start}-${end} of ${total} groups`}
              </span>
              <span>score version {feed.data.items[0]?.security.score_version ?? "security-v1"}</span>
            </div>

            <div className="grid gap-3">
              {feed.data.items.map((story) => (
                <SecurityStoryRow key={story.security.group_key} story={story} />
              ))}
            </div>

            {feed.data.items.length === 0 && (
              <p className="mt-8 text-sm text-slate-500">
                No accepted security groups in this section.
              </p>
            )}

            <div className="mt-5 flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={!canPrev}
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700
                           hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-xs text-slate-500">Page {page + 1}</span>
              <button
                type="button"
                onClick={() => setPage((p) => p + 1)}
                disabled={!canNext}
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700
                           hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function SecurityHotCard({ story, rank }: { story: SecurityItem; rank: number }) {
  const { item, security } = story;
  const excerpt = item.summary ?? item.excerpt;
  return (
    <article
      className="min-w-0 rounded-lg border border-white/10 bg-white/[0.06] p-3
                 transition hover:-translate-y-0.5 hover:border-brand-amber/70 hover:bg-white/[0.09]"
    >
      <div className="mb-2 flex items-center gap-2 text-[11px] text-slate-300">
        <span className="rounded bg-brand-amber px-2 py-0.5 font-bold text-slate-950">
          #{rank}
        </span>
        <SourceCount story={story} dark />
        <span className="ml-auto tabular-nums text-brand-amber">
          {score(security.security_hot_score)}
        </span>
      </div>
      <h3 className="line-clamp-2 font-serif text-sm font-bold leading-snug sm:text-base">
        <SecurityLink story={story} className="hover:text-brand-amber" />
      </h3>
      <BadgeList badges={security.badges} dark />
      {excerpt && (
        <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-slate-300">
          {excerpt}
        </p>
      )}
      <WhyList reasons={security.why_ranked} dark />
    </article>
  );
}

function SecurityStoryRow({ story }: { story: SecurityItem }) {
  const { item, security } = story;
  const excerpt = item.summary ?? item.excerpt;
  return (
    <article className="min-w-0 rounded-lg border border-slate-200 bg-white p-4 transition hover:shadow-sm sm:p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className="rounded bg-slate-950 px-2 py-0.5 font-semibold uppercase tracking-wide text-white">
          {sectionLabel(security.section)}
        </span>
        {item.source_name && <span className="truncate">{item.source_name}</span>}
        <span>{dateText(security.event_time ?? item.published_at ?? item.fetched_at)}</span>
        <SourceCount story={story} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
        <div className="min-w-0">
          <h3 className="font-serif text-base font-bold leading-snug text-slate-950 sm:text-lg">
            <SecurityLink story={story} className="hover:text-brand" />
          </h3>
          {excerpt && <p className="mt-2 text-sm leading-relaxed text-slate-600">{excerpt}</p>}
          <BadgeList badges={security.badges} />
          <WhyList reasons={security.why_ranked} />
        </div>

        <div className="grid gap-2 text-xs">
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
      className={
        `group relative inline-flex outline-none ${
          dark
            ? "rounded border border-white/10 bg-white/[0.06] px-1.5 py-0.5 text-slate-300"
            : "rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-emerald-700"
        }`
      }
      title={title}
      aria-label={title}
    >
      {story.source_count} {plural}
      <span
        className={`pointer-events-none absolute left-0 top-[calc(100%+6px)] z-30 hidden w-72 max-w-[calc(100vw-2rem)]
                    rounded-md border px-3 py-2 text-left text-[11px] leading-relaxed shadow-lg
                    group-hover:block group-focus:block ${
                      dark
                        ? "border-white/10 bg-slate-900 text-slate-100"
                        : "border-slate-200 bg-white text-slate-700"
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
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-medium text-slate-600 underline decoration-dotted underline-offset-4">
          {label}
        </span>
        <span className={`tabular-nums ${strong ? "font-bold text-slate-950" : "text-slate-500"}`}>
          {score(value)}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`${strong ? "bg-brand" : "bg-slate-500"} h-full rounded-full`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div
        className="pointer-events-none absolute bottom-[calc(100%+6px)] right-0 z-30 hidden w-80 max-w-[calc(100vw-2rem)]
                   rounded-md border border-slate-200 bg-white px-3 py-2 text-[11px] leading-relaxed text-slate-700
                   shadow-lg group-hover:block group-focus:block"
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
          className={`max-w-full truncate rounded px-2 py-0.5 text-[11px] ${
            dark
              ? "border border-white/10 bg-white/[0.08] text-slate-200"
              : "border border-slate-200 bg-slate-50 text-slate-700"
          }`}
        >
          {badge}
        </span>
      ))}
    </div>
  );
}

function WhyList({ reasons, dark = false }: { reasons: string[]; dark?: boolean }) {
  if (reasons.length === 0) return null;
  return (
    <div className={`mt-3 flex flex-wrap gap-1.5 text-[11px] ${dark ? "text-slate-300" : "text-slate-500"}`}>
      {reasons.slice(0, 4).map((reason) => (
        <span key={reason} className={dark ? "text-slate-300" : "text-slate-500"}>
          {reason}
        </span>
      ))}
    </div>
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
      `Soft-article penalty ${score(security.soft_article_score)}.`,
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
