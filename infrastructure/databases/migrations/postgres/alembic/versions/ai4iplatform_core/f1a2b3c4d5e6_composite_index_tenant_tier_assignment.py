"""composite_index_tenant_tier_assignment

Every billing event (deduct_balance) and every assign/reassign call filters
ppu_tenant_tier_assignments by:
    tenant_id = :tenant_id AND effective_from <= now() AND effective_to > now()

The existing single-column index on tenant_id lets Postgres find all rows
for a tenant but still has to check effective_from/effective_to per row via
the heap. Replacing it with a composite index on
(tenant_id, effective_from, effective_to) lets that whole WHERE clause be
satisfied from the index directly, which matters once a tenant accumulates
many historical rows from repeated reassignments.

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        'ix_ppu_tenant_tier_assignments_tenant_id',
        table_name='ppu_tenant_tier_assignments',
    )
    op.create_index(
        'ix_ppu_tenant_tier_assignments_tenant_effective',
        'ppu_tenant_tier_assignments',
        ['tenant_id', 'effective_from', 'effective_to'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_ppu_tenant_tier_assignments_tenant_effective',
        table_name='ppu_tenant_tier_assignments',
    )
    op.create_index(
        'ix_ppu_tenant_tier_assignments_tenant_id',
        'ppu_tenant_tier_assignments',
        ['tenant_id'],
    )
