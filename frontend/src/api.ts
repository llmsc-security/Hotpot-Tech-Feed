import type { ContentType, ItemList } from "./types";

// In dev, Vite proxies /api/* → http://localhost:8000.
// In prod, set VITE_API_BASE to an absolute URL (e.g. https://feed.ai2wj.com).
const BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/$/, "");

export type SortKey = "date_desc" | "date_asc" | "fetched_desc" | "fetched_asc";

export interface ListItemsParams {
  limit?: number;
  offset?: number;
  topic?: string;
  content_type?: ContentType;
  source_id?: string;
  source?: string;
  year?: number;
  q?: string;
  sort?: SortKey;
}

export interface NLFilter {
  topic?: string;
  content_type?: ContentType;
  source?: string;
  year?: number;
  q?: string;
  sort?: SortKey;
}

export async function listItems(params: ListItemsParams = {}): Promise<ItemList> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const url = `${BASE}/items${qs.size ? `?${qs}` : ""}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`GET ${url} → ${resp.status}`);
  return resp.json();
}

export interface SourceSummary {
  id: string;
  name: string;
  url: string;
  kind: "arxiv" | "rss" | "html" | "github";
  language: string;
  lab: string | null;
  trust_score: number;
  health_status: "ok" | "degraded" | "broken" | "unknown";
  status: "active" | "probation" | "paused";
  last_fetched_at: string | null;
  item_count: number;
}

export interface SourceListResp {
  sources: SourceSummary[];
  total: number;
}

export async function listSources(): Promise<SourceListResp> {
  const resp = await fetch(`${BASE}/sources`);
  if (!resp.ok) throw new Error(`sources fetch failed: ${resp.status}`);
  return resp.json();
}

export interface Stats {
  items: number;
  sources: number;
}

export async function getStats(): Promise<Stats> {
  const resp = await fetch(`${BASE}/stats`);
  if (!resp.ok) throw new Error(`stats fetch failed: ${resp.status}`);
  return resp.json();
}

export interface YearBucket {
  year: number;
  count: number;
}

export async function getYears(): Promise<YearBucket[]> {
  const resp = await fetch(`${BASE}/items/years`);
  if (!resp.ok) throw new Error(`years fetch failed: ${resp.status}`);
  return resp.json();
}

export async function nlSearch(query: string): Promise<NLFilter> {
  const resp = await fetch(`${BASE}/items/nl-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!resp.ok) throw new Error(`nl-search failed: ${resp.status}`);
  return resp.json();
}

export interface RecentSearch {
  query: string;
  last_used_at: string;
}

export async function recentSearches(limit = 20): Promise<RecentSearch[]> {
  const resp = await fetch(`${BASE}/items/recent-searches?limit=${limit}`);
  if (!resp.ok) throw new Error(`recent-searches failed: ${resp.status}`);
  return resp.json();
}

export interface ContributeResult {
  ok: boolean;
  duplicate: boolean;
  item_id: string;
  title: string;
  content_type: string;
  topics: string[];
  tags: string[];
}

export class ContributeError extends Error {
  hint?: string;
  constructor(message: string, hint?: string) {
    super(message);
    this.hint = hint;
  }
}

export async function contributeUrl(url: string): Promise<ContributeResult> {
  const resp = await fetch(`${BASE}/contribute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (resp.status === 422) {
    const body = await resp.json().catch(() => ({}));
    const detail = body?.detail ?? {};
    throw new ContributeError(detail.message ?? "Invalid URL", detail.hint);
  }
  if (!resp.ok) {
    throw new ContributeError(`Server error (${resp.status}). Please try again.`);
  }
  return resp.json();
}
