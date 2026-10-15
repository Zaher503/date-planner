"""Places keep what the venue's website says: price tiers, price notes and the hours as worded

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-14 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("places", sa.Column("hours_text", sa.Text(), nullable=True))
    op.add_column("places", sa.Column("price_text", sa.Text(), nullable=True))
    op.add_column("places", sa.Column("price_tiers", postgresql.JSONB(), server_default="[]", nullable=False))


def downgrade() -> None:
    op.drop_column("places", "price_tiers")
    op.drop_column("places", "price_text")
    op.drop_column("places", "hours_text")
