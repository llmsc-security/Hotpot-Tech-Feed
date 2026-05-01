"""security item scores

Revision ID: 0007_security_item_scores
Revises: 0006_item_exposure
Create Date: 2026-05-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0007_security_item_scores"
down_revision = "0006_item_exposure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_item_scores",
        sa.Column("item_id", UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("accepted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reject_reason", sa.String(length=160), nullable=True),
        sa.Column("score_version", sa.String(length=32), server_default="security-v1", nullable=False),
        sa.Column("group_key", sa.String(length=256), nullable=False),
        sa.Column("representative_item_id", UUID(as_uuid=True), nullable=True),
        sa.Column("section", sa.String(length=64), server_default="all", nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("security_relevance_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("evidence_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("exploitation_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("content_quality_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("impact_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("actionability_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("source_authority_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("freshness_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("corroboration_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("soft_article_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("final_security_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("security_hot_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("badges", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("why_ranked", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source_chain", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("features", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_security_item_scores_accepted", "security_item_scores", ["accepted"])
    op.create_index("ix_security_item_scores_event_time", "security_item_scores", ["event_time"])
    op.create_index("ix_security_item_scores_final_security_score", "security_item_scores", ["final_security_score"])
    op.create_index("ix_security_item_scores_security_hot_score", "security_item_scores", ["security_hot_score"])
    op.create_index("ix_security_item_scores_section", "security_item_scores", ["section"])
    op.create_index("ix_security_scores_accepted_final_event", "security_item_scores", ["accepted", "final_security_score", "event_time"])
    op.create_index("ix_security_scores_accepted_hot", "security_item_scores", ["accepted", "security_hot_score"])
    op.create_index("ix_security_scores_group_key", "security_item_scores", ["group_key"])
    op.create_index("ix_security_scores_section_final", "security_item_scores", ["section", "accepted", "final_security_score"])


def downgrade() -> None:
    op.drop_index("ix_security_scores_section_final", table_name="security_item_scores")
    op.drop_index("ix_security_scores_group_key", table_name="security_item_scores")
    op.drop_index("ix_security_scores_accepted_hot", table_name="security_item_scores")
    op.drop_index("ix_security_scores_accepted_final_event", table_name="security_item_scores")
    op.drop_index("ix_security_item_scores_section", table_name="security_item_scores")
    op.drop_index("ix_security_item_scores_security_hot_score", table_name="security_item_scores")
    op.drop_index("ix_security_item_scores_final_security_score", table_name="security_item_scores")
    op.drop_index("ix_security_item_scores_event_time", table_name="security_item_scores")
    op.drop_index("ix_security_item_scores_accepted", table_name="security_item_scores")
    op.drop_table("security_item_scores")
