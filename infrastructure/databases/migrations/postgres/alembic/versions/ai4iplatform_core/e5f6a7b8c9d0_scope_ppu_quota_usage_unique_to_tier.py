"""scope_ppu_quota_usage_unique_to_tier

Widens the uniqueness rule on ppu_quota_usage from
(tenant_id, inference_name, billing_month) to
(tenant_id, inference_name, billing_month, tier_id).

This is required for Tier Reassignment: when a tenant's active tier changes
mid-month, usage/cost must start a fresh row under the new tier instead of
accumulating into the previous tier's row.

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        'uq_ppu_quota_usage_tenant_inference_month',
        'ppu_quota_usage',
        type_='unique',
    )
    op.create_unique_constraint(
        'uq_ppu_quota_usage_tenant_inference_month_tier',
        'ppu_quota_usage',
        ['tenant_id', 'inference_name', 'billing_month', 'tier_id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_ppu_quota_usage_tenant_inference_month_tier',
        'ppu_quota_usage',
        type_='unique',
    )
    op.create_unique_constraint(
        'uq_ppu_quota_usage_tenant_inference_month',
        'ppu_quota_usage',
        ['tenant_id', 'inference_name', 'billing_month'],
    )
