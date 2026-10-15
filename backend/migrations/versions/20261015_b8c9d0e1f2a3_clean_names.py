"""Names read from captions lose the punctuation around them ("Bacari W Adams?")

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-15 09:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.textclean import clean_name

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    for table, col in (("places", "name"), ("events", "title")):
        rows = conn.execute(sa.text(f"SELECT id, {col} FROM {table} WHERE {col} ~ '[?!]\s*$'")).all()
        for id_, name in rows:
            clean = clean_name(name)
            if clean and clean != name:
                conn.execute(sa.text(f"UPDATE {table} SET {col} = :n WHERE id = :i"), {"n": clean, "i": id_})


def downgrade() -> None:
    pass
