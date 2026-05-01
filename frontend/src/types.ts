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

export type SecuritySection =
  | "all"
  | "exploited_now"
  | "new_important_cves"
  | "real_attack_cases"
  | "technical_analysis"
  | "vendor_advisories"
  | "oss_package_vulnerabilities";

export type SecuritySort = "score_desc" | "hot_desc" | "date_desc";

export interface SecurityScore {
  accepted: boolean;
  reject_reason: string | null;
  score_version: string;
  group_key: string;
  section: SecuritySection;
  event_time: string | null;
  security_relevance_score: number;
  evidence_score: number;
  exploitation_score: number;
  content_quality_score: number;
  impact_score: number;
  actionability_score: number;
  source_authority_score: number;
  freshness_score: number;
  corroboration_score: number;
  soft_article_score: number;
  final_security_score: number;
  security_hot_score: number;
  badges: string[];
  why_ranked: string[];
  source_chain: string[];
}

export interface SecurityItem {
  item: Item;
  security: SecurityScore;
  support_count: number;
  source_count: number;
  sources: string[];
  matched_titles: string[];
}

export interface SecurityItemList {
  items: SecurityItem[];
  total: number;
  limit: number;
  offset: number;
}
