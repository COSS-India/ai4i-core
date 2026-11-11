"""merge audit_logs and default configs seed heads

Revision ID: c4e6a8b0d2f1
Revises: 97c3bf253272, a3c5e7f9b1d4
Create Date: 2026-11-11 00:00:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'c4e6a8b0d2f1'
down_revision: Union[str, Sequence[str], None] = ('97c3bf253272', 'a3c5e7f9b1d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
