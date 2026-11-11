"""create audit_logs table

One audit table for every service (ai4i_core.audit). Each row records one
change to one entity: its state before and after, the acting user and the
request's trace id. A reason given with the change (e.g. tenants.reason
for a tenant status change) is part of the snapshots, not a column.
entity_name / action hold ai4i_core.audit enum values as plain VARCHAR so a
new entity or action needs no migration.

Revision ID: 97c3bf253272
Revises: b7d3f1a9c2e5
Create Date: 2026-11-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "97c3bf253272"
down_revision: Union[str, None] = "b7d3f1a9c2e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "audit_logs"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("entity_name", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("previous_state", postgresql.JSONB(), nullable=True),
        sa.Column("new_state", postgresql.JSONB(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("performed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_audit_logs_entity",
        TABLE,
        ["entity_name", "entity_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_audit_logs_created_at", TABLE, ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name=TABLE)
    op.drop_index("ix_audit_logs_entity", table_name=TABLE)
    op.drop_table(TABLE)
