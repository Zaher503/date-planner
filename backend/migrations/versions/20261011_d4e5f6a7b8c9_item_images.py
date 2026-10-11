"""item_images: per-item hero picture candidates; item_sources.mention_at

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-11 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("item_sources", sa.Column("mention_at", sa.Float(), nullable=True))
    op.create_table(
        "item_images",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("place_id", sa.UUID(), nullable=True),
        sa.Column("event_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("at_seconds", sa.Float(), nullable=True),
        sa.Column("rank", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("chosen", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint("num_nonnulls(place_id, event_id) = 1", name="one_item"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_item_images_place", "item_images", ["place_id"])
    op.create_index("ix_item_images_event", "item_images", ["event_id"])
    op.create_index("ix_item_images_source", "item_images", ["source_id"])


def downgrade() -> None:
    op.drop_table("item_images")
    op.drop_column("item_sources", "mention_at")
