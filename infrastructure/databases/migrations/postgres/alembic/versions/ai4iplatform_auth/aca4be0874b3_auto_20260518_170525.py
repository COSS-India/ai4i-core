"""auto_20260518_170525

Revision ID: aca4be0874b3
Revises: c4e8f1a2b3d0
Create Date: 2026-05-18 11:35:26.815026

No-op: tenants.status default and enum type are applied in c4e8f1a2b3d0 (parent revision).
Autogenerate emitted a redundant ALTER; kept for DBs that already applied this revision.
See MIGRATION_CHAIN.md.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'aca4be0874b3'
down_revision: Union[str, None] = 'c4e8f1a2b3d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
