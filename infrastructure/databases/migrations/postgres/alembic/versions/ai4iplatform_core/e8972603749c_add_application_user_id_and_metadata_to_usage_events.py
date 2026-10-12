"""add application_user_id and metadata to usage_events

application_user_id (varchar 64) is the end user of the calling application,
as the application identifies them; metadata (jsonb) carries free-form
attributes of the event. Both are nullable, so existing rows and writers that
don't set them are unaffected.

Added on the partitioned parent: Postgres adds each column to every attached
partition, the DEFAULT one included, and to every partition created later, so
no partition is altered by name. Adding a nullable column without a default
only touches the catalog, not the rows.

The GIN index on metadata (jsonb_ops, for @>, ?, ?| and ?& queries) is also
created on the parent, so Postgres builds it on every existing partition and
on each one the partition jobs create later. CREATE INDEX CONCURRENTLY isn't
supported on a partitioned parent; the column is empty when the index is
built, so the lock is brief.

Revision ID: e8972603749c
Revises: cf2715437b4f
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8972603749c"
down_revision: Union[str, None] = "cf2715437b4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "usage_events"
INDEX = "ix_usage_events_metadata_gin"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("application_user_id", sa.String(64), nullable=True))
    op.add_column(TABLE, sa.Column("metadata", postgresql.JSONB(), nullable=True))
    op.create_index(INDEX, TABLE, ["metadata"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, "metadata")
    op.drop_column(TABLE, "application_user_id")
