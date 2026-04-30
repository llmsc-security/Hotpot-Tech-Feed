"""items.click_count: how many times users clicked through to the canonical URL

Revision ID: 0004_click_count
Revises: 0003_primary_category
Create Date: 2026-05-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_click_count"
down_revision = "0003_primary_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column(
            "click_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index("ix_items_click_count", "items", ["click_count"])


def downgrade() -> None:
    op.drop_index("ix_items_click_count", table_name="items")
    op.drop_column("items", "click_count")
