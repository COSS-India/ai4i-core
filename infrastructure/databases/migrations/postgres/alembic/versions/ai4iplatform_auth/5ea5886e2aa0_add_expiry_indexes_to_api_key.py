"""add the expiry indexes of the key-expiry reminders

The two partial indexes let the daily reminder queries read only the keys
whose expiry falls in the next few days, not the whole table.

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


def upgrade() -> None:
    op.create_index(
        "ix_api_key_rotated_key_expires_at",
        "api_key",
        ["rotated_key_expires_at"],
        postgresql_where=sa.text("rotated_key IS NOT NULL AND is_active"),
    )
    op.create_index(
        "ix_api_key_expires_at",
        "api_key",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL AND is_active"),
    )


def downgrade() -> None:
    op.drop_index("ix_api_key_expires_at", table_name="api_key")
    op.drop_index("ix_api_key_rotated_key_expires_at", table_name="api_key")
