"""initial schema: sources, items, item_tags

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False, unique=True),
        sa.Column(
            "kind",
            sa.Enum("arxiv", "rss", "html", "github", name="source_kind"),
            nullable=False,
        ),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("lab", sa.String(200), nullable=True),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trust_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column(
            "health_status",
            sa.Enum("ok", "degraded", "broken", "unknown", name="health_status"),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "status",
            sa.Enum("active", "probation", "paused", name="source_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("failure_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("canonical_url", sa.String(2048), nullable=False, unique=True),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("authors", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("excerpt", sa.Text, nullable=True),
        sa.Column("raw_html_path", sa.String(1024), nullable=True),
        sa.Column(
            "content_type",
            sa.Enum(
                "paper", "blog", "news", "lab_announcement", "tutorial", "oss_release", "other",
                name="content_type",
            ),
            nullable=False,
            server_default="other",
        ),
        sa.Column("lab", sa.String(200), nullable=True),
        sa.Column("venue", sa.String(200), nullable=True),
        sa.Column("dedup_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_canonical", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("embedding_id", sa.String(64), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("commentary", sa.Text, nullable=True),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Float, nullable=False, server_default="0.0"),
    )
    op.create_index("ix_items_published_at", "items", ["published_at"])
    op.create_index("ix_items_dedup_group", "items", ["dedup_group_id"])

    op.create_table(
        "item_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("tag", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(16), nullable=False, server_default="llm"),
    )
    op.create_index("ix_item_tags_tag", "item_tags", ["tag"])


def downgrade() -> None:
    op.drop_index("ix_item_tags_tag", table_name="item_tags")
    op.drop_table("item_tags")
    op.drop_index("ix_items_dedup_group", table_name="items")
    op.drop_index("ix_items_published_at", table_name="items")
    op.drop_table("items")
    op.drop_table("sources")
    sa.Enum(name="content_type").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="source_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="health_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="source_kind").drop(op.get_bind(), checkfirst=False)
