"""add BRIN index on usage_events.occurred_at

The Usage Dashboard's Today queries filter usage_events on occurred_at alone
(all institutions, or every key of one institution), but every existing index
leads with tenant_id, api_key_id or service_id, so each request scanned the
whole current-month partition to sum one day.

BRIN fits: rows are appended in roughly occurred_at order by the billing
consumer, so each block range covers a narrow time span and the index stays a
few pages per partition. Created on the partitioned parent, so Postgres adds it
to every existing partition and to each one the partition job creates later.
(CREATE INDEX CONCURRENTLY isn't supported on a partitioned parent; the table
is small this early, so the brief lock is acceptable.)

autosummarize = on: BRIN only summarises a block range at VACUUM, and an
unsummarised range matches every query. The consumer appends continuously, so
without it the newest ranges — the ones Today reads — stay unsummarised until
autovacuum gets round to the partition, and range scans read the whole
partition. With it, each range is queued for summarising as soon as it fills.
The option carries over to every partition's index.

Revision ID: cf2715437b4f
Revises: d1e3f5a7b9c2
Create Date: 2026-10-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = "cf2715437b4f"
down_revision: Union[str, None] = "d1e3f5a7b9c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "ix_usage_events_occurred_at_brin"


def upgrade() -> None:
    op.create_index(
        INDEX, "usage_events", ["occurred_at"],
        postgresql_using="brin", postgresql_with={"autosummarize": "on"},
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="usage_events")
