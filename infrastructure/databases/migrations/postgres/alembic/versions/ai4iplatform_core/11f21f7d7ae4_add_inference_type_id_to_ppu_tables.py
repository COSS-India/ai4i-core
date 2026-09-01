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

All three are phase 2, and phase 2 is blocked until the NULL audit below comes
back clean.

The backfill joins on lower(inference_name): platform-core compares
case-insensitively (tier_service.py), so mixed-case rows can exist.

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
        op.create_index(
            f"ix_{table}_inference_type_id",
            table,
            ["inference_type_id"],
        )
        op.execute(
            f"UPDATE {table} t SET inference_type_id = it.id"
            "  FROM inference_types it"
            f" WHERE it.name = lower(t.inference_name)"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_inference_type_id", table_name=table)
        op.drop_constraint(f"fk_{table}_inference_type_id", table, type_="foreignkey")
        op.drop_column(table, "inference_type_id")
