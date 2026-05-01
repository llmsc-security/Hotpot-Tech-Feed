"""Application settings loaded from environment / .env.

All knobs live here. Anything secret (DB password, Gmail app password, LLM API
key) must come from the environment — never commit real values to .env.
"""
from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_ingest_workers() -> int:
    # LLM-bound: half the CPU cores, capped so a big host doesn't melt
    # the upstream LLM endpoint (override via INGEST_WORKERS or --workers).
    return max(1, min(32, (os.cpu_count() or 2) // 2))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Core ----------
    env: str = "dev"
    log_level: str = "INFO"

    # ---------- Database ----------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "hotpot"
    postgres_user: str = "hotpot"
    postgres_password: str = "hotpot"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ---------- Redis / Celery ----------
    redis_url: str = "redis://localhost:6379/0"

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url

    # ---------- Qdrant ----------
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "hotpot_items"

    # ---------- LLM (Qwen via OpenAI-compatible endpoint) ----------
    openai_base_url: str = "https://api.ai2wj.com/v1"
    openai_api_key: str = "sk-placeholder"
    llm_model_tagger: str = "Qwen/Qwen3.5-397B-A17B"
    llm_model_summary: str = "Qwen/Qwen3.5-397B-A17B"
    llm_model_commentary: str = "Qwen/Qwen3.5-397B-A17B"
    llm_timeout_s: float = 30.0

    # ---------- Ingest concurrency ----------
    # Per-item enrichment is LLM-bound; default to half the available CPU cores.
    ingest_workers: int = Field(default_factory=_default_ingest_workers)
    # Source-level concurrency is sequential by default — one source at a time,
    # with full ingest_workers on its items.
    ingest_source_workers: int = 1

    # ---------- Embeddings ----------
    # Set to false in early dev if you don't want to pull the bge-m3 weights.
    embeddings_enabled: bool = False
    embeddings_model: str = "BAAI/bge-m3"
    embeddings_dim: int = 1024

    # ---------- Email (Resend SMTP via send.ai2wj.com) ----------
    smtp_host: str = "smtp.resend.com"
    smtp_port: int = 465
    smtp_use_tls: bool = True
    smtp_username: str = "resend"
    smtp_password: str = "re_placeholder"  # Resend API key
    digest_from_email: str = "digest@ai2wj.com"
    digest_from_name: str = "Hotpot Tech Feed"
    digest_reply_to: str = "noreply@ai2wj.com"

    # ---------- Crawler ----------
    user_agent: str = (
        "HotpotTechFeed/0.1 (+https://feed.ai2wj.com; contact: jornbowrl@gmail.com)"
    )
    http_timeout_s: float = 20.0

    # ---------- Pipeline knobs ----------
    dedup_title_threshold: float = 0.90
    dedup_embedding_threshold: float = 0.92
    dedup_window_days: int = 7
    enrich_summary: bool = True
    enrich_commentary: bool = False  # off until prompts are tuned (Phase 5)

    # ---------- Site ----------
    public_origin: str = "http://localhost:5173"

    # ---------- Source discovery ----------
    # Optional GitHub token (read-only public scope) — without it, GitHub API
    # mining is rate-limited to 60 req/h. Recommended for any real cadence.
    github_token: str = ""
    # Bias the LLM verdict on candidate sources: "llm" (foundation models),
    # "academic" (paper-level depth), "ml-systems", etc.
    discovery_focus: str = "llm,academic"
    discovery_languages: str = "en,zh"
    discovery_seed_path: str = "data/seed_candidates.yaml"
    # Self-hosted RSSHub for WeChat / Bilibili / Zhihu bridge feeds.
    # Empty string = disabled (default until you bring up the rsshub service).
    rsshub_url: str = ""
    # Quality-scoring thresholds for auto-probation / auto-pause.
    score_probation_threshold: float = 0.2
    score_pause_after_n_low_runs: int = 2


settings = Settings()
