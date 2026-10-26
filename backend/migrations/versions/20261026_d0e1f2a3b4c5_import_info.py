"""Record which importer and model read each place and event

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-26 14:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY = ("jsonb_build_object('importer_version', 'unknown', 'engine', 'legacy', 'model', 'unknown', "
          "'at', to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"+00:00\"'), 'history', '[]'::jsonb)")


def upgrade() -> None:
    for table in ("places", "events"):
        op.add_column(table, sa.Column("import_info", JSONB(), nullable=False, server_default="{}"))
        # Rows saved before this column existed: the importer is not known, only when they were created
        op.execute(f"UPDATE {table} SET import_info = {LEGACY}")


def downgrade() -> None:
    for table in ("events", "places"):
        op.drop_column(table, "import_info")
