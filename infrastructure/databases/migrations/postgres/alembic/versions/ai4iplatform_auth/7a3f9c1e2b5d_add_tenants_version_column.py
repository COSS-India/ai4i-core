"""add_tenants_version_column

Revision ID: 7a3f9c1e2b5d
Revises: 51c538d423cf
Create Date: 2026-08-27 16:00:00.000000

Adds tenants.version — an optimistic-lock counter for the new PATCH
/auth/tenants/{tenant_id}/budget endpoint's optional expected_version
check. No prior migration created this column (there was no optimistic-
locking column anywhere in the schema before this).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a3f9c1e2b5d'
down_revision: Union[str, None] = '51c538d423cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tenants',
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('tenants', 'version')
