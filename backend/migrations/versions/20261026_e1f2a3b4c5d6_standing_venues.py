"""Standing venues: a place whose website is re-read on a schedule for new events

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-26 18:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("places", sa.Column("standing", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("places", sa.Column("watch_url", sa.Text()))
    op.add_column("places", sa.Column("watch_source_id", UUID(as_uuid=True),
                                      sa.ForeignKey("sources.id", ondelete="SET NULL")))
    op.add_column("places", sa.Column("watch_every_days", sa.Integer(), nullable=False, server_default="7"))
    op.add_column("places", sa.Column("watch_parser", sa.Text()))
    op.add_column("places", sa.Column("last_scanned_at", sa.DateTime(timezone=True)))
    op.add_column("places", sa.Column("last_scan_status", sa.Text()))
    op.add_column("places", sa.Column("last_scan_note", sa.Text()))
    op.create_check_constraint("watch_every_days_range", "places", "watch_every_days BETWEEN 1 AND 90")
    op.create_index("ix_places_standing", "places", ["standing"], postgresql_where=sa.text("standing"))
    op.add_column("events", sa.Column("listed", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("events", sa.Column("last_seen_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("events", "last_seen_at")
    op.drop_column("events", "listed")
    op.drop_index("ix_places_standing", table_name="places")
    op.drop_constraint("watch_every_days_range", "places", type_="check")
    for col in ("last_scan_note", "last_scan_status", "last_scanned_at", "watch_parser", "watch_every_days",
                "watch_source_id", "watch_url", "standing"):
        op.drop_column("places", col)
