"""revoke api keys whose current value alone was revoked

Revision ID: b8a1957cd6a3
Revises: e7a1b2c3d4f5
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b8a1957cd6a3"
down_revision: Union[str, None] = "e7a1b2c3d4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE api_key SET is_active = false WHERE api_key_revoked_at IS NOT NULL AND is_active")


def downgrade() -> None:
    # A revoke can't be undone safely: the row may also have been revoked as a whole.
    pass
