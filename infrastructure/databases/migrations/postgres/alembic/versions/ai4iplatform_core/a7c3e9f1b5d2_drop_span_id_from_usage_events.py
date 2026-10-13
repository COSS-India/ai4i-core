"""drop span_id from usage_events; primary key (correlation_id, occurred_at)

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
