import { bumpItemClick } from "../api";
import { ExternalIcon, FlameIcon } from "./HotpotIcons";
import type { Item } from "../types";

const CONTENT_TYPE_LABEL: Record<string, string> = {
  paper: "Paper",
  blog: "Blog",
  news: "News",
  lab_announcement: "Lab",
  tutorial: "Tutorial",
  oss_release: "OSS",
  other: "Other",
};

export default function ItemCard({ item }: { item: Item }) {
  const topic = item.tags.find((t) => t.tag.startsWith("topic:"))?.tag.slice(6);
  const subTags = item.tags.filter((t) => !t.tag.startsWith("topic:")).slice(0, 3);
  const dateStr = (item.published_at ?? item.fetched_at).slice(0, 10);
  const excerpt = item.summary ?? item.excerpt;

  return (
    <article className="gx-row-card cursor-default">
      <span className="gx-rank" title={CONTENT_TYPE_LABEL[item.content_type] ?? item.content_type}>
        {(CONTENT_TYPE_LABEL[item.content_type] ?? item.content_type).slice(0, 1)}
      </span>

      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-[var(--gx-muted)]">
          <span className="gx-chip gx-chip-chili px-2 py-0.5 text-[10px] uppercase tracking-wide">
            {CONTENT_TYPE_LABEL[item.content_type] ?? item.content_type}
          </span>
          {topic && <span className="gx-chip px-2 py-0.5 text-[11px]">{topic}</span>}
          {item.source_name && <span className="max-w-[180px] truncate">{item.source_name}</span>}
          <span>{dateStr}</span>
        </div>

        <h3 className="gx-section-title line-clamp-2 text-base font-bold leading-snug text-[var(--gx-ink)] sm:text-lg">
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

        {excerpt && (
          <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-[var(--gx-ink-2)]">
            {excerpt}
          </p>
        )}

        {(item.authors.length > 0 || subTags.length > 0) && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--gx-muted)]">
            {item.authors.length > 0 && (
              <span className="max-w-full truncate">
                {item.authors.slice(0, 3).join(", ")}
                {item.authors.length > 3 ? " et al." : ""}
              </span>
            )}
            {subTags.map((t) => (
              <span key={t.tag} className="gx-chip px-2 py-0.5 text-[10px]">
                {t.tag}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex shrink-0 flex-row items-center gap-2 sm:flex-col sm:items-end">
        {(item.exposure_count > 1 || item.click_count > 0) && (
          <div className="flex flex-wrap justify-end gap-1.5 text-[11px]">
            {item.exposure_count > 1 && (
              <span
                className="gx-chip gx-chip-emerald px-2 py-0.5"
                title={(item.exposure_sources ?? []).slice(0, 8).join(", ")}
              >
                {item.exposure_count} sources
              </span>
            )}
            {item.click_count > 0 && (
              <span
                className="gx-chip gx-chip-amber px-2 py-0.5"
                title={`${item.click_count} click${item.click_count === 1 ? "" : "s"}`}
              >
                <FlameIcon size={11} />
                {item.click_count}
              </span>
            )}
          </div>
        )}
        <a
          href={item.canonical_url}
          target="_blank"
          rel="noreferrer"
          className="gx-btn min-h-0 px-2 py-1 text-[11px]"
          onClick={() => bumpItemClick(item.id)}
          aria-label={`Open ${item.title}`}
        >
          <ExternalIcon size={12} />
        </a>
      </div>
    </article>
  );
}
