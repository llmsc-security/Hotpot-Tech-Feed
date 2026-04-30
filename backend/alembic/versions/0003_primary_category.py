"""items.primary_category: the user-confirmed top-level category for each item

Revision ID: 0003_primary_category
Revises: 0002_search_logs
Create Date: 2026-04-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_primary_category"
down_revision = "0002_search_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("primary_category", sa.String(64), nullable=True),
    )
    op.create_index("ix_items_primary_category", "items", ["primary_category"])

    # Backfill: pick the highest-confidence non-Other topic tag per item.
    op.execute("""
        UPDATE items i
        SET primary_category = sub.cat
        FROM (
            SELECT DISTINCT ON (item_id) item_id,
                   substring(tag from 7) AS cat
            FROM item_tags
            WHERE tag LIKE 'topic:%' AND tag <> 'topic:Other'
            ORDER BY item_id, confidence DESC
        ) sub
        WHERE i.id = sub.item_id
          AND i.primary_category IS NULL;
    """)
    # Anything still NULL falls back to "Other".
    op.execute("UPDATE items SET primary_category = 'Other' WHERE primary_category IS NULL;")


def downgrade() -> None:
    op.drop_index("ix_items_primary_category", table_name="items")
    op.drop_column("items", "primary_category")
