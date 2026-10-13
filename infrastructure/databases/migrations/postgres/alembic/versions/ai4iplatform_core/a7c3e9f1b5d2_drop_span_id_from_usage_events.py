"""drop span_id from usage_events: one row per request

The inference service now emits one billable ai-inference span per request,
carrying the request's summed units; services that call the model more than
once per request (TTS chunks, per-item audio) record each call as an
ai-inference-call child span, which the billing consumer ignores. With one
billed span per request, span_id no longer tells rows apart, so the primary
key becomes (correlation_id, occurred_at). occurred_at is the span's end time
and is identical on a Kafka redelivery, so a redelivered span still hits the
key and writes nothing (ON CONFLICT DO NOTHING). Postgres requires the
partition column in every unique key, which occurred_at is.

Existing rows: rows written before this change keep one row per span (a
chunked TTS request stays several rows, each with its own occurred_at). Two
rows can only collide on the new key if two spans of one correlation id
ended in the same microsecond. The migration doesn't guess how to combine
them: it checks first and stops with an error listing them, before changing
anything, so they can be resolved by hand (DUPLICATES_SQL finds them all).

Locking: dropping and re-adding the primary key on the partitioned parent
rebuilds the unique index on every partition under an exclusive lock, so
writes to usage_events wait for the duration. The billing consumer's insert
runs in a savepoint and retries through Kafka, so nothing is lost.

downgrade() restores span_id with a constant placeholder; (correlation_id,
occurred_at) is unique at that point, so the old key accepts every row.

Revision ID: a7c3e9f1b5d2
Revises: e8972603749c
Create Date: 2026-10-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9f1b5d2"
down_revision: Union[str, None] = "e8972603749c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "usage_events"
PK = "pk_usage_events"
# span_id restored on downgrade for rows written while it didn't exist.
_PLACEHOLDER_SPAN_ID = "0000000000000000"

# Rows that would share a key once span_id is gone.
DUPLICATES_SQL = (
    f"SELECT correlation_id, occurred_at, count(*) AS rows FROM {TABLE}"
    " GROUP BY correlation_id, occurred_at HAVING count(*) > 1"
)
_EXAMPLES = 5


def _fail_on_duplicates() -> None:
    """Stop before any change when rows would collide on the new key."""
    if op.get_context().as_sql:   # --sql: no data to check
        return
    rows = op.get_bind().execute(sa.text(f"{DUPLICATES_SQL} LIMIT {_EXAMPLES + 1}")).all()
    if not rows:
        return
    examples = "\n".join(
        f"  correlation_id={r.correlation_id} occurred_at={r.occurred_at} rows={r.rows}"
        for r in rows[:_EXAMPLES]
    )
    more = "\n  ..." if len(rows) > _EXAMPLES else ""
    raise RuntimeError(
        f"{TABLE} has rows sharing (correlation_id, occurred_at), which the new primary key "
        f"won't allow. Nothing was changed. Merge or delete them by hand, then run the "
        f"migration again.\n{examples}{more}\nFind them all with:\n  {DUPLICATES_SQL};"
    )


def upgrade() -> None:
    _fail_on_duplicates()
    op.drop_constraint(PK, TABLE, type_="primary")
    op.drop_column(TABLE, "span_id")
    op.create_primary_key(PK, TABLE, ["correlation_id", "occurred_at"])


def downgrade() -> None:
    # A constant default is stored in the catalog, not written to each row.
    op.add_column(
        TABLE,
        sa.Column("span_id", sa.String(32), nullable=False, server_default=_PLACEHOLDER_SPAN_ID),
    )
    op.alter_column(TABLE, "span_id", server_default=None)
    op.drop_constraint(PK, TABLE, type_="primary")
    op.create_primary_key(PK, TABLE, ["correlation_id", "span_id", "occurred_at"])
