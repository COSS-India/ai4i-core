"""index_usage_dashboard_queries

The PPU usage dashboard (usage-summary / usage-tenants / usage-tenant) runs two
queries with no efficient index path today:

1. get_tenant_tier_usage_breakdown filters ppu_quota_usage by
   `billing_month = :month AND tenant_id IN (:tenant_ids)`. ppu_quota_usage has
   no index on billing_month at all, and its unique constraint leads with
   tenant_id, not billing_month. When the admin view omits tier_id, tenant_ids
   is effectively every tenant on the platform, so the tenant_id predicate
   filters almost nothing and Postgres has no efficient path to just this
   month's rows — it falls back to scanning the whole (ever-growing) table.
   A composite index on (billing_month, tenant_id) lets it jump straight to
   the queried month.

2. get_tenant_tier_as_of_period_end ranks ppu_tenant_tier_assignments rows
   with `effective_from <= :end AND effective_to > :end`, with no tenant_id
   predicate in the common (unfiltered) admin view. The existing composite
   index on (tenant_id, effective_from, effective_to) — added for the
   single-tenant billing/assignment paths that always filter by tenant_id
   first — doesn't help here since tenant_id isn't part of this query's WHERE
   clause. A composite index on (effective_from, effective_to) lets the
   window-function ranking start from just the rows covering the queried
   instant instead of scanning every historical assignment across every
   tenant.

Revision ID: c8d9e0f1a2b3
Revises: b7e2c9a4f1d3
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, Sequence[str], None] = 'b7e2c9a4f1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_ppu_quota_usage_billing_month_tenant',
        'ppu_quota_usage',
        ['billing_month', 'tenant_id'],
    )
    op.create_index(
        'ix_ppu_tenant_tier_assignments_effective_window',
        'ppu_tenant_tier_assignments',
        ['effective_from', 'effective_to'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_ppu_tenant_tier_assignments_effective_window',
        table_name='ppu_tenant_tier_assignments',
    )
    op.drop_index(
        'ix_ppu_quota_usage_billing_month_tenant',
        table_name='ppu_quota_usage',
    )
