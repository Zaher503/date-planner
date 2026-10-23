"""Events state a minimum age (18 or 21) when the page says so

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-23 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("min_age", sa.SmallInteger(), nullable=True))
    op.create_check_constraint("min_age_valid", "events", "min_age IS NULL OR min_age IN (18, 21)")


def downgrade() -> None:
    op.drop_constraint("min_age_valid", "events", type_="check")
    op.drop_column("events", "min_age")
