"""auto_20260427_182007

Revision ID: b73fa8d05c10
Revises: fa6fd0aca3a2
Create Date: 2026-04-27 18:20:08.237563

No-op: api_key table is created with String(32) and expires_at in the initial migration (03c373bdd881).
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'b73fa8d05c10'
down_revision: Union[str, None] = 'fa6fd0aca3a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
