"""Add unique index on lower(organisation) in tenants table

Enforces organisation-name uniqueness at the database level (case-insensitive).
Complements the app-level duplicate checks in create_tenant and update_tenant,
closing TOCTOU race conditions under concurrent requests.

The index expression lower(organisation) matches the case-insensitive lookup
used in TenantRepository.get_by_organisation.

NOTE: This migration will fail if duplicate (case-insensitive) organisation
names already exist in the tenants table. Deduplicate before applying.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_tenants_organisation_lower "
        "ON tenants (lower(organisation))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tenants_organisation_lower")
