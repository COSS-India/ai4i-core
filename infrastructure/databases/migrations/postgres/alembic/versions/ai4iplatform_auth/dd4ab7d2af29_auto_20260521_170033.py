"""auto_20260521_170033

Revision ID: dd4ab7d2af29
Revises: 5f775ba90435
Create Date: 2026-05-21 11:30:35.855286

No-op: same redundant tenants.status autogenerate as 5f775ba90435 / aca4be0874b3.
Keeping this revision preserves the chain if it was already applied locally.
"""
from typing import Sequence, Union

revision: str = 'dd4ab7d2af29'
down_revision: Union[str, None] = '5f775ba90435'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
