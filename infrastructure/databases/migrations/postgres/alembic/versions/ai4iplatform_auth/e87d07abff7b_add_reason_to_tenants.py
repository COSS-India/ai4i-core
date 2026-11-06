"""add tenants.reason

PATCH /auth/tenants/{id}/status now requires a reason when an institution is
suspended or deactivated: the predefined reason from the suspend-reasons /
deactivate-reasons config, or the admin's own text when they pick Other.
Activating takes an optional reason; without one the column is cleared.
It describes the latest status change only. Existing rows stay NULL.

Revision ID: e87d07abff7b
Revises: e8b9c0d1e2f3
Create Date: 2026-11-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e87d07abff7b"
down_revision: Union[str, None] = "e8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("reason", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "reason")
