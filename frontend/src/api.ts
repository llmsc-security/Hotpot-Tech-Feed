import type {
  ContentType,
  HotItem,
  ItemList,
  SecurityItem,
  SecurityItemList,
  SecuritySection,
  SecuritySort,
} from "./types";

// In dev, Vite proxies /api/* → http://localhost:8000.
// In prod, set VITE_API_BASE to an absolute URL (e.g. https://feed.ai2wj.com).
const BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/$/, "");

export type SortKey = "smart" | "date_desc" | "date_asc" | "fetched_desc" | "fetched_asc";

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

export async function listHotItems(
  opts: { limit?: number; windowDays?: number } = {},
): Promise<HotItem[]> {
  const qs = new URLSearchParams();
  qs.set("limit", String(opts.limit ?? 20));
  qs.set("window_days", String(opts.windowDays ?? 14));
  const resp = await fetch(`${BASE}/items/hot?${qs}`);
  if (!resp.ok) throw new Error(`hot items fetch failed: ${resp.status}`);
  return resp.json();
}

export async function listSecurityHot(
  opts: { limit?: number } = {},
): Promise<SecurityItem[]> {
  const qs = new URLSearchParams();
  qs.set("limit", String(opts.limit ?? 10));
  const resp = await fetch(`${BASE}/security/hot?${qs}`);
  if (!resp.ok) throw new Error(`security hot fetch failed: ${resp.status}`);
  return resp.json();
}

export async function listSecurityItems(
  opts: {
    limit?: number;
    offset?: number;
    section?: SecuritySection;
    sort?: SecuritySort;
  } = {},
): Promise<SecurityItemList> {
  const qs = new URLSearchParams();
  qs.set("limit", String(opts.limit ?? 25));
  qs.set("offset", String(opts.offset ?? 0));
  qs.set("section", opts.section ?? "all");
  qs.set("sort", opts.sort ?? "score_desc");
  const resp = await fetch(`${BASE}/security/items?${qs}`);
  if (!resp.ok) throw new Error(`security items fetch failed: ${resp.status}`);
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

export async function listSources(
  opts: { category?: string | null } = {}
): Promise<SourceListResp> {
  const qs = new URLSearchParams();
  if (opts.category) qs.set("category", opts.category);
  const url = `${BASE}/sources${qs.size ? `?${qs}` : ""}`;
  const resp = await fetch(url);
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

export async function nlSearch(
  query: string,
  opts: { record?: boolean } = {}
): Promise<NLFilter> {
  const body: { query: string; record?: boolean } = { query };
  if (opts.record === false) body.record = false;
  const resp = await fetch(`${BASE}/items/nl-search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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

export interface ItemSuggestion {
  type: "recent_query" | "source" | "topic" | "tag" | "title" | "idea" | string;
  label: string;
  query: string;
  detail: string | null;
}

export async function itemSuggestions(
  query: string,
  opts: { limit?: number; includeRecent?: boolean } = {},
): Promise<ItemSuggestion[]> {
  const qs = new URLSearchParams();
  qs.set("q", query);
  qs.set("limit", String(opts.limit ?? 10));
  if (opts.includeRecent) qs.set("include_recent", "true");
  const resp = await fetch(`${BASE}/items/suggest?${qs}`);
  if (!resp.ok) throw new Error(`suggestions failed: ${resp.status}`);
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

export interface CategoryCandidate {
  category: string;
  confidence: number;
  open?: boolean;
}

export interface ClassifyResult {
  duplicate: boolean;
  url: string;
  title: string;
  excerpt: string | null;
  candidates: CategoryCandidate[];
  content_type: string;
  tags: string[];
  // duplicate-only:
  item_id?: string;
  primary_category?: string | null;
}

export interface CommitInput {
  url: string;
  title: string;
  excerpt: string | null;
  category: string | null;
  candidates: CategoryCandidate[];
  content_type: string;
  tags: string[];
}

export async function classifyContribute(url: string): Promise<ClassifyResult> {
  const resp = await fetch(`${BASE}/contribute/classify`, {
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

export interface RecategorizeResult {
  ok: boolean;
  item_id: string;
  primary_category: string;
}

export async function recategorizeContribution(
  itemId: string,
  category: string,
): Promise<RecategorizeResult> {
  const resp = await fetch(`${BASE}/contribute/recategorize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item_id: itemId, category }),
  });
  if (resp.status === 422) {
    const body = await resp.json().catch(() => ({}));
    const detail = body?.detail ?? {};
    throw new ContributeError(detail.message ?? "Could not recategorize", detail.hint);
  }
  if (!resp.ok) {
    throw new ContributeError(`Server error (${resp.status}). Please try again.`);
  }
  return resp.json();
}

export async function commitContribute(input: CommitInput): Promise<ContributeResult> {
  const resp = await fetch(`${BASE}/contribute/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (resp.status === 422) {
    const body = await resp.json().catch(() => ({}));
    const detail = body?.detail ?? {};
    throw new ContributeError(detail.message ?? "Could not commit", detail.hint);
  }
  if (!resp.ok) {
    throw new ContributeError(`Server error (${resp.status}). Please try again.`);
  }
  return resp.json();
}

export interface CategoryBucket {
  category: string;
  count: number;
}

export async function listCategories(): Promise<CategoryBucket[]> {
  const resp = await fetch(`${BASE}/items/categories`);
  if (!resp.ok) throw new Error(`categories fetch failed: ${resp.status}`);
  return resp.json();
}

export interface ContentTypeBucket {
  content_type: string;
  count: number;
}

export async function listContentTypes(): Promise<ContentTypeBucket[]> {
  const resp = await fetch(`${BASE}/items/content-types`);
  if (!resp.ok) throw new Error(`content-types fetch failed: ${resp.status}`);
  return resp.json();
}

export type CommunitySort = "hot" | "recent";

export async function listCommunity(
  opts: { sort?: CommunitySort; limit?: number; offset?: number } = {},
): Promise<ItemList> {
  const qs = new URLSearchParams();
  qs.set("sort", opts.sort ?? "hot");
  qs.set("limit", String(opts.limit ?? 50));
  if (opts.offset) qs.set("offset", String(opts.offset));
  const resp = await fetch(`${BASE}/items/community?${qs}`);
  if (!resp.ok) throw new Error(`community fetch failed: ${resp.status}`);
  return resp.json();
}

export interface SourceCandidate {
  id: string;
  domain: string;
  sample_url: string;
  name_hint: string | null;
  language: string | null;
  mention_count: number;
  contributor_count: number;
  signal_score: number;
  llm_verdict: string | null;
  llm_rationale: string | null;
  is_llm_focused: boolean;
  academic_depth: string | null;
  suggested_kind: string | null;
  status: string;
  source_signal: string | null;
}

export interface CandidateListResp {
  candidates: SourceCandidate[];
  total: number;
}

export async function listCandidates(
  status: "pending" | "promoted" | "rejected" = "pending",
  limit = 50,
): Promise<CandidateListResp> {
  const resp = await fetch(`${BASE}/discovery/candidates?status=${status}&limit=${limit}`);
  if (!resp.ok) throw new Error(`candidates fetch failed: ${resp.status}`);
  return resp.json();
}

export async function promoteCandidate(
  id: string,
  kind?: "rss" | "html" | "arxiv" | "github",
): Promise<{ ok: boolean; source_id: string; name: string; url: string }> {
  const resp = await fetch(`${BASE}/discovery/candidates/${id}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(kind ? { kind } : {}),
  });
  if (!resp.ok) throw new Error(`promote failed: ${resp.status}`);
  return resp.json();
}

export async function rejectCandidate(id: string): Promise<void> {
  const resp = await fetch(`${BASE}/discovery/candidates/${id}/reject`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error(`reject failed: ${resp.status}`);
}

export async function bumpItemClick(itemId: string): Promise<void> {
  // Fire-and-forget — never let a tracking failure block the user's navigation.
  try {
    await fetch(`${BASE}/items/${itemId}/click`, { method: "POST", keepalive: true });
  } catch {
    /* ignore */
  }
}
