"""source_candidates + source_quality_runs + Source.editorial_focus

Revision ID: 0005_source_discovery
Revises: 0004_click_count
Create Date: 2026-05-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0005_source_discovery"
down_revision = "0004_click_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- editorial_focus on Source ----
    op.add_column(
        "sources",
        sa.Column("editorial_focus", JSONB, nullable=True),
    )

    # ---- source_candidates ----
    op.create_table(
        "source_candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("domain", sa.String(255), nullable=False, unique=True),
        sa.Column("sample_url", sa.String(2048), nullable=False),
        sa.Column("name_hint", sa.String(255), nullable=True),
        sa.Column("oa_name", sa.String(255), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("mention_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("contributor_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("signal_score", sa.Float, server_default="0", nullable=False),
        sa.Column("llm_verdict", sa.String(16), nullable=True),
        sa.Column("llm_rationale", sa.Text, nullable=True),
        sa.Column("is_llm_focused", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("academic_depth", sa.String(8), nullable=True),
        sa.Column("suggested_kind", sa.String(16), nullable=True),
        sa.Column("suggested_rss_url", sa.String(2048), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("promoted_to_source_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_signal", sa.String(32), nullable=True),
    )
    op.create_index("ix_source_candidates_status", "source_candidates", ["status"])
    op.create_index("ix_source_candidates_signal_score", "source_candidates", ["signal_score"])

    # ---- source_quality_runs ----
    op.create_table(
        "source_quality_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ctr_30d", sa.Float, server_default="0", nullable=False),
        sa.Column("median_clicks_30d", sa.Float, server_default="0", nullable=False),
        sa.Column("item_count_30d", sa.Integer, server_default="0", nullable=False),
        sa.Column("llm_noise_ratio", sa.Float, nullable=True),
        sa.Column("llm_rationale", sa.Text, nullable=True),
        sa.Column("trust_score_before", sa.Float, nullable=False),
        sa.Column("trust_score_after", sa.Float, nullable=False),
        sa.Column("action_taken", sa.String(32), nullable=True),
    )
    op.create_index("ix_source_quality_runs_source_id", "source_quality_runs", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_source_quality_runs_source_id", table_name="source_quality_runs")
    op.drop_table("source_quality_runs")
    op.drop_index("ix_source_candidates_signal_score", table_name="source_candidates")
    op.drop_index("ix_source_candidates_status", table_name="source_candidates")
    op.drop_table("source_candidates")
    op.drop_column("sources", "editorial_focus")
