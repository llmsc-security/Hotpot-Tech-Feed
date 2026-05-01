export type ContentType =
  | "paper"
  | "blog"
  | "news"
  | "lab_announcement"
  | "tutorial"
  | "oss_release"
  | "other";

export interface Tag {
  tag: string;
  confidence: number;
  source: string;
}

export interface Item {
  id: string;
  source_id: string;
  source_name: string | null;
  canonical_url: string;
  title: string;
  authors: string[];
  published_at: string | null;
  fetched_at: string;
  language: string;
  excerpt: string | null;
  content_type: ContentType;
  primary_category: string | null;
  lab: string | null;
  venue: string | null;
  summary: string | null;
  commentary: string | null;
  score: number;
  click_count: number;
  exposure_count: number;
  exposure_sources: string[];
  tags: Tag[];
}

export interface ItemList {
  items: Item[];
  total: number;
  limit: number;
  offset: number;
}

export interface HotItem {
  item: Item;
  hot_score: number;
  support_count: number;
  source_count: number;
  sources: string[];
  topic: string;
  matched_titles: string[];
}
