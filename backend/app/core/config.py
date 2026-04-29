"""Application settings loaded from environment / .env.

All knobs live here. Anything secret (DB password, Gmail app password, LLM API
key) must come from the environment — never commit real values to .env.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    llm_model_tagger: str = "qwen3.6"
    llm_model_summary: str = "qwen3.6"
    llm_model_commentary: str = "qwen3.6"
    llm_timeout_s: float = 30.0

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


settings = Settings()
