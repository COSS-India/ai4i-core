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
chunked TTS request stays several rows, each with its own occurred_at). Rows
that would collide on the new key (same correlation_id and occurred_at, a
microsecond-level coincidence) are merged first: units and costs are added
onto the row with the lowest span_id and the others deleted, so totals are
unchanged. The units CHECK still holds, since it holds for each part.

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

_SUMMED = (
    "total_units", "cached_input_units", "output_units",
    "input_units_cost", "cached_input_units_cost", "output_units_cost",
)


def upgrade() -> None:
    # Merge rows that would collide on the new key into the lowest span_id.
    op.execute(
        "CREATE TEMP TABLE usage_events_dup ON COMMIT DROP AS"
        " SELECT correlation_id, occurred_at, min(span_id) AS keep_span_id, "
        + ", ".join(f"sum({c}) AS {c}" for c in _SUMMED)
        + f" FROM {TABLE} GROUP BY correlation_id, occurred_at HAVING count(*) > 1"
    )
    op.execute(
        f"UPDATE {TABLE} u SET "
        + ", ".join(f"{c} = d.{c}" for c in _SUMMED)
        + " FROM usage_events_dup d"
        " WHERE u.correlation_id = d.correlation_id AND u.occurred_at = d.occurred_at"
        " AND u.span_id = d.keep_span_id"
    )
    op.execute(
        f"DELETE FROM {TABLE} u USING usage_events_dup d"
        " WHERE u.correlation_id = d.correlation_id AND u.occurred_at = d.occurred_at"
        " AND u.span_id <> d.keep_span_id"
    )
    # Dropped now rather than at commit: alembic may run more steps in this
    # transaction (e.g. a downgrade and upgrade again).
    op.execute("DROP TABLE usage_events_dup")

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
