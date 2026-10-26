"""drop api_key_revoked_at from api_key

Revision ID: b8a1957cd6a3
Revises: e7a1b2c3d4f5
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8a1957cd6a3"
down_revision: Union[str, None] = "e7a1b2c3d4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A key whose current value was revoked on its own is revoked as a whole.
    op.execute("UPDATE api_key SET is_active = false WHERE api_key_revoked_at IS NOT NULL AND is_active")
    op.drop_column("api_key", "api_key_revoked_at")


def downgrade() -> None:
    op.add_column("api_key", sa.Column("api_key_revoked_at", sa.DateTime(timezone=True), nullable=True))
