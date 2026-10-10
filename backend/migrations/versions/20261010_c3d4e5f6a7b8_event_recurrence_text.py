"""events.recurrence_text: recurrence as written, until it is turned into an RRULE

Revision ID: c3d4e5f6a7b8
Revises: 7b1e2c9d4a10
Create Date: 2026-10-10 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "7b1e2c9d4a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("recurrence_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "recurrence_text")
