"""Item pictures may come from Google Places (no source) and carry an author credit

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-02 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("item_images", "source_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("item_images", sa.Column("attribution", sa.Text()))


def downgrade() -> None:
    op.execute("DELETE FROM item_images WHERE source_id IS NULL")
    op.drop_column("item_images", "attribution")
    op.alter_column("item_images", "source_id", existing_type=sa.UUID(), nullable=False)
