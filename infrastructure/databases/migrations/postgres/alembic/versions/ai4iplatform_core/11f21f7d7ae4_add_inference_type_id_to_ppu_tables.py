"""add_inference_type_id_to_ppu_tables

Adds a NULLABLE ``inference_type_id`` FK to ``tier_quotas`` and ``quota_usage``
and backfills it from ``inference_name``. Deliberately does NOT:

  * SET NOT NULL — the backfill cannot resolve rows whose inference_name is
    absent from the catalogue. _billing.py documents that ``inference_name=''``
    rows occur whenever mm_services.task_type is unset.
  * add a unique constraint on the new column — with nullable ids that would
    give quota_usage two competing conflict targets, and NULL never equals NULL
    in a unique match.
  * drop inference_name — every read path still uses it, including the raw
    upsert SQL in payperuse_consumer.

All three are phase 2, which is blocked on **two** things, not one:

  1. ``payperuse_consumer`` setting ``inference_type_id`` on its ``quota_usage``
     upsert. It does NOT today — its INSERT column list is
     ``(id, tenant_id, inference_name, billing_month, monthly_quota_snap,
     monthly_quota_used, tier_id)``. So in this revision the column is
     **backfill-only**: existing rows get a value from the UPDATE below, and
     every row written afterwards carries NULL.
  2. The NULL audit below coming back clean — which cannot happen while (1) is
     outstanding, however many times it is re-run. Accruing NULLs here are
     expected, not a migration bug.

The backfill joins on lower(inference_name): platform-core compares
case-insensitively (tier_service.py), so mixed-case rows can exist.

**The FK indexes are NOT created here.** A plain CREATE INDEX takes a SHARE lock
that blocks INSERT/UPDATE/DELETE for the whole build, and this revision also runs
a row-locking backfill UPDATE — both held until commit. payperuse_consumer writes
quota_usage on every billed span, so it would stall for the duration. The indexes
are built CONCURRENTLY in the next revision instead.

Revision ID: 11f21f7d7ae4
Revises: 52eb3034332e
Create Date: 2026-08-31 15:49:03.882914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '11f21f7d7ae4'
down_revision: Union[str, None] = '52eb3034332e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = ("tier_quotas", "quota_usage")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("inference_type_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_inference_type_id",
            table,
            "inference_types",
            ["inference_type_id"],
            ["id"],
        )
        op.execute(
            f"UPDATE {table} t SET inference_type_id = it.id"
            "  FROM inference_types it"
            f" WHERE it.name = lower(t.inference_name)"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"fk_{table}_inference_type_id", table, type_="foreignkey")
        op.drop_column(table, "inference_type_id")
