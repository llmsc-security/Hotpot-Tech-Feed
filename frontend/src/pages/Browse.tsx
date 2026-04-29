import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { listItems } from "../api";
import ItemCard from "../components/ItemCard";
import type { ContentType } from "../types";

const TOPICS = ["ML", "Systems", "Theory", "Security", "HCI", "PL", "DB", "Networks", "Graphics", "Robotics"];
const CTYPES: { value: ContentType | ""; label: string }[] = [
  { value: "", label: "All types" },
  { value: "paper", label: "Papers" },
  { value: "blog", label: "Blogs" },
  { value: "news", label: "News" },
  { value: "lab_announcement", label: "Lab announcements" },
  { value: "tutorial", label: "Tutorials" },
  { value: "oss_release", label: "OSS releases" },
];

export default function Browse() {
  const [topic, setTopic] = useState<string>("");
  const [contentType, setContentType] = useState<ContentType | "">("");
  const [q, setQ] = useState<string>("");

  const params = {
    limit: 50,
    offset: 0,
    topic: topic ? `topic:${topic}` : undefined,
    content_type: contentType || undefined,
    q: q || undefined,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["items", params],
    queryFn: () => listItems(params),
  });

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <input
          type="text"
          placeholder="Search titles…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="border border-slate-300 rounded-md px-3 py-2 text-sm flex-1 min-w-[200px]"
        />
        <select
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          <option value="">All topics</option>
          {TOPICS.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select
          value={contentType}
          onChange={(e) => setContentType(e.target.value as ContentType | "")}
          className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white"
        >
          {CTYPES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {error && (
        <p className="text-sm text-red-600">
          Failed to load items. Is the backend running on :8000?
        </p>
      )}

      {data && (
        <>
          <p className="text-xs text-slate-500 mb-4">
            {data.total} item{data.total === 1 ? "" : "s"} · showing {data.items.length}
          </p>
          <div className="grid gap-4">
            {data.items.map((it) => (
              <ItemCard key={it.id} item={it} />
            ))}
          </div>
          {data.items.length === 0 && (
            <p className="text-sm text-slate-500 mt-8">
              No items yet. Run <code className="bg-slate-100 px-1 rounded">hotpot ingest-now</code> on the backend.
            </p>
          )}
        </>
      )}
    </div>
  );
}
