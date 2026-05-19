"""seed_default_data

Revision ID: 96cd009dcbf3
Revises: 1136a6462a4d
Create Date: 2026-05-18 15:50:03.048242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96cd009dcbf3'
down_revision: Union[str, None] = '1136a6462a4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO smr_tenant_policies (tenant_id, latency_policy, cost_policy, accuracy_policy)
        VALUES
            ('tenant-a', 'low',    'tier_3', 'sensitive'),
            ('tenant-b', 'high',   'tier_1', 'standard'),
            ('tenant-c', 'medium', 'tier_2', 'standard')
        ON CONFLICT (tenant_id) DO NOTHING
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DELETE FROM smr_tenant_policies
        WHERE tenant_id IN ('tenant-a', 'tenant-b', 'tenant-c')
    """))
