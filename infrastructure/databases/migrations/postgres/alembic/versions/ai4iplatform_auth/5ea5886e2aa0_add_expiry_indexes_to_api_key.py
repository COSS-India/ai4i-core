"""add the expiry indexes of the key-expiry reminders

The two partial indexes let the daily reminder queries read only the keys
whose expiry falls in the next few days, not the whole table.

Built CONCURRENTLY, so api_key stays writable during the build. CONCURRENTLY
can't run in a transaction: autocommit_block (env.py runs each migration in
its own transaction, transaction_per_migration=True).

Revision ID: 5ea5886e2aa0
Revises: e87d07abff7b
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "5ea5886e2aa0"
down_revision: Union[str, None] = "e87d07abff7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# index name -> (column, partial-index predicate)
_INDEXES = {
    "ix_api_key_rotated_key_expires_at": ("rotated_key_expires_at", "rotated_key IS NOT NULL AND is_active"),
    "ix_api_key_expires_at": ("expires_at", "expires_at IS NOT NULL AND is_active"),
}


def _drop_if_invalid(conn, index_name: str) -> None:
    """Drop an INVALID index left by an earlier failed CONCURRENTLY build;
    otherwise CREATE ... IF NOT EXISTS would skip it and keep it unusable."""
    invalid = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_index i"
            "  JOIN pg_class c ON c.oid = i.indexrelid"
            " WHERE c.relname = :name AND NOT i.indisvalid"
        ),
        {"name": index_name},
    ).first()
    if invalid:
        conn.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"'))


def upgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for index_name, (column, predicate) in _INDEXES.items():
            _drop_if_invalid(conn, index_name)
            conn.execute(
                sa.text(
                    f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}"'
                    f" ON api_key ({column}) WHERE {predicate}"
                )
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for index_name in reversed(list(_INDEXES)):
            conn.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"'))
