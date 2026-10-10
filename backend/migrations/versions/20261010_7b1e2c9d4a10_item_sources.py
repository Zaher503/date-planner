"""item_sources link table; candidates tied to a place

A list video ("10 date ideas in LA") mentions several places, so sources no longer
point at a single place or event.

Revision ID: 7b1e2c9d4a10
Revises: 2c0040aef50e
Create Date: 2026-10-10 11:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b1e2c9d4a10"
down_revision: str | None = "2c0040aef50e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "item_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("place_id", sa.UUID(), nullable=True),
        sa.Column("event_id", sa.UUID(), nullable=True),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.CheckConstraint("num_nonnulls(place_id, event_id) = 1", name="one_item"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_item_sources_place", "item_sources", ["source_id", "place_id"], unique=True,
                    postgresql_where=sa.text("place_id IS NOT NULL"))
    op.create_index("uq_item_sources_event", "item_sources", ["source_id", "event_id"], unique=True,
                    postgresql_where=sa.text("event_id IS NOT NULL"))
    op.create_index("ix_item_sources_place", "item_sources", ["place_id"])
    op.create_index("ix_item_sources_event", "item_sources", ["event_id"])

    op.drop_index("ix_sources_place_id", table_name="sources")
    op.drop_index("ix_sources_event_id", table_name="sources")
    op.drop_constraint("sources_place_id_fkey", "sources", type_="foreignkey")
    op.drop_constraint("sources_event_id_fkey", "sources", type_="foreignkey")
    op.drop_column("sources", "place_id")
    op.drop_column("sources", "event_id")

    op.add_column("candidates", sa.Column("place_id", sa.UUID(), nullable=True))
    op.add_column("candidates", sa.Column("item_index", sa.SmallInteger(), server_default="0", nullable=False))
    op.create_foreign_key("candidates_place_id_fkey", "candidates", "places", ["place_id"], ["id"],
                          ondelete="CASCADE")
    op.create_index("ix_candidates_place_id", "candidates", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_candidates_place_id", table_name="candidates")
    op.drop_constraint("candidates_place_id_fkey", "candidates", type_="foreignkey")
    op.drop_column("candidates", "item_index")
    op.drop_column("candidates", "place_id")

    op.add_column("sources", sa.Column("event_id", sa.UUID(), nullable=True))
    op.add_column("sources", sa.Column("place_id", sa.UUID(), nullable=True))
    op.create_foreign_key("sources_event_id_fkey", "sources", "events", ["event_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("sources_place_id_fkey", "sources", "places", ["place_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_sources_event_id", "sources", ["event_id"])
    op.create_index("ix_sources_place_id", "sources", ["place_id"])

    op.drop_index("ix_item_sources_event", table_name="item_sources")
    op.drop_index("ix_item_sources_place", table_name="item_sources")
    op.drop_index("uq_item_sources_event", table_name="item_sources")
    op.drop_index("uq_item_sources_place", table_name="item_sources")
    op.drop_table("item_sources")
