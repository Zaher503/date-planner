"""Descriptions carry no emoji: clean the ones already saved

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-14 18:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.textclean import strip_emoji

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    for table in ("places", "events"):
        rows = conn.execute(sa.text(f"SELECT id, description FROM {table} WHERE description IS NOT NULL")).all()
        for id_, text in rows:
            clean = strip_emoji(text)
            if clean != text:
                conn.execute(sa.text(f"UPDATE {table} SET description = :d WHERE id = :i"), {"d": clean, "i": id_})


def downgrade() -> None:
    pass  # the emoji are gone for good
