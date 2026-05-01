"""item exposure signals

Revision ID: 0006_item_exposure
Revises: 0005_source_discovery
Create Date: 2026-05-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_item_exposure"
down_revision = "0005_source_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("exposure_count", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "items",
        sa.Column("exposure_sources", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.create_index("ix_items_exposure_count", "items", ["exposure_count"])


def downgrade() -> None:
    op.drop_index("ix_items_exposure_count", table_name="items")
    op.drop_column("items", "exposure_sources")
    op.drop_column("items", "exposure_count")
