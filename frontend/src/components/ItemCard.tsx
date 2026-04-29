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

  return (
    <article className="bg-white border border-slate-200 rounded-lg p-5 hover:shadow-sm transition">
      <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
        <span className="px-2 py-0.5 rounded-full bg-brand-tint text-brand font-semibold uppercase tracking-wide">
          {CONTENT_TYPE_LABEL[item.content_type] ?? item.content_type}
        </span>
        {topic && (
          <span className="px-2 py-0.5 rounded-full bg-slate-100">{topic}</span>
        )}
        {item.source_name && <span className="truncate">{item.source_name}</span>}
        <span>·</span>
        <time>{dateStr}</time>
      </div>

      <h3 className="font-serif text-lg font-bold leading-snug">
        <a
          href={item.canonical_url}
          target="_blank"
          rel="noreferrer"
          className="hover:text-brand"
        >
          {item.title}
        </a>
      </h3>

      {item.summary ? (
        <p className="mt-2 text-sm text-slate-700">{item.summary}</p>
      ) : item.excerpt ? (
        <p className="mt-2 text-sm text-slate-500 line-clamp-3">{item.excerpt}</p>
      ) : null}

      {(item.authors.length > 0 || subTags.length > 0) && (
        <div className="mt-3 flex items-center gap-3 text-xs text-slate-500 flex-wrap">
          {item.authors.length > 0 && (
            <span className="truncate">
              {item.authors.slice(0, 3).join(", ")}
              {item.authors.length > 3 ? " et al." : ""}
            </span>
          )}
          {subTags.map((t) => (
            <span key={t.tag} className="px-2 py-0.5 rounded bg-slate-50 border border-slate-200">
              {t.tag}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}
