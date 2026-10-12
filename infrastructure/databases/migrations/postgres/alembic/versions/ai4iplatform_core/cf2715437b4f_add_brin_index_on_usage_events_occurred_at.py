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

Revision ID: cf2715437b4f
Revises: 9092247a3b27
Create Date: 2026-10-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = "cf2715437b4f"
down_revision: Union[str, None] = "9092247a3b27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "ix_usage_events_occurred_at_brin"


def upgrade() -> None:
    op.create_index(INDEX, "usage_events", ["occurred_at"], postgresql_using="brin")


def downgrade() -> None:
    op.drop_index(INDEX, table_name="usage_events")
