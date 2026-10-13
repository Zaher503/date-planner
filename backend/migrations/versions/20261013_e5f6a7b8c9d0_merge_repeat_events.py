"""Fold events that are the same show on different dates into one event with several occurrences

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-13 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEY = "regexp_replace(lower(title), '[^a-z0-9]+', '', 'g')"


def upgrade() -> None:
    db = op.get_bind()
    groups = db.execute(sa.text(f"""
        SELECT array_agg(id ORDER BY created_at, id) FROM events
        WHERE place_id IS NOT NULL AND starts_at IS NOT NULL AND review_status <> 'dismissed'
        GROUP BY place_id, {KEY} HAVING count(*) > 1""")).scalars().all()
    for ids in groups:
        keep, dupes = ids[0], ids[1:]
        for d in dupes:  # one at a time: two dupes can share a source
            p = {"keep_id": str(keep), "dupes": [str(d)]}
            db.execute(sa.text("""
                INSERT INTO occurrences (event_id, starts_at, ends_at)
                SELECT CAST(:keep_id AS uuid), starts_at, ends_at FROM occurrences WHERE event_id = ANY(CAST(:dupes AS uuid[]))
                ON CONFLICT ON CONSTRAINT uq_occurrence DO NOTHING"""), p)
            db.execute(sa.text("""
                UPDATE item_sources SET event_id = CAST(:keep_id AS uuid) WHERE event_id = ANY(CAST(:dupes AS uuid[]))
                  AND source_id NOT IN (SELECT source_id FROM item_sources WHERE event_id = CAST(:keep_id AS uuid))"""), p)
            db.execute(sa.text("""
                UPDATE user_item_state SET event_id = CAST(:keep_id AS uuid) WHERE event_id = ANY(CAST(:dupes AS uuid[]))
                  AND user_id NOT IN (SELECT user_id FROM user_item_state WHERE event_id = CAST(:keep_id AS uuid))"""), p)
            db.execute(sa.text("""
                UPDATE item_images SET event_id = CAST(:keep_id AS uuid), chosen = false WHERE event_id = ANY(CAST(:dupes AS uuid[]))"""), p)
            db.execute(sa.text("DELETE FROM events WHERE id = ANY(CAST(:dupes AS uuid[]))"), p)
        p = {"keep_id": str(keep)}
        # The event shows its earliest date
        db.execute(sa.text("""
            UPDATE events e SET starts_at = o.starts_at, ends_at = o.ends_at
            FROM (SELECT starts_at, ends_at FROM occurrences WHERE event_id = CAST(:keep_id AS uuid)
                  ORDER BY starts_at LIMIT 1) o
            WHERE e.id = CAST(:keep_id AS uuid) AND NOT jsonb_exists(e.user_overrides, 'starts_at')"""), p)


def downgrade() -> None:
    pass  # merged events are not split again
