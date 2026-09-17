"""add tenant_plans created_by

Revision ID: 569df8229653
Revises: e0f1a2b3c4d5
Create Date: 2026-09-16 20:09:35.604019

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '569df8229653'
down_revision: Union[str, None] = 'e0f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Audit-trail parity with every other admin-inserted table (applications,
    # api_key, tenants, ...) — tenant_plans was the one insert item #2's
    # created_by threading couldn't cover, since the column didn't exist yet.
    op.add_column(
        'tenant_plans',
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('tenant_plans', 'created_by')
