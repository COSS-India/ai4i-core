"""Add unique index on lower(email) in tenants table

Enforces tenant email uniqueness at the database level (case-insensitive).
Complements the app-level duplicate checks in create_tenant and update_tenant
to close TOCTOU race conditions under concurrent requests.

The index expression lower(email) matches the case-insensitive lookup
used in TenantRepository.get_by_email.

NOTE: This migration will fail if duplicate (case-insensitive) email addresses
already exist in the tenants table. Deduplicate before applying.

Revision ID: e5f6a7b8c9d0
Revises: e3f4a5b6c7d8
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_tenants_email_lower "
        "ON tenants (lower(email))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tenants_email_lower")
