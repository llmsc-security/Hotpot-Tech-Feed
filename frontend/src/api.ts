import type { ContentType, ItemList } from "./types";

// In dev, Vite proxies /api/* → http://localhost:8000.
// In prod, set VITE_API_BASE to an absolute URL (e.g. https://feed.ai2wj.com).
const BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/$/, "");

export interface ListItemsParams {
  limit?: number;
  offset?: number;
  topic?: string;
  content_type?: ContentType;
  source_id?: string;
  q?: string;
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

export async function listSources() {
  const resp = await fetch(`${BASE}/sources`);
  if (!resp.ok) throw new Error(`sources fetch failed: ${resp.status}`);
  return resp.json();
}
