"""add_budget_usage_api_key_id_index

Revision ID: 36e2308271e1
Revises: d4e5f6a7b8c9
Create Date: 2026-08-27 15:00:00.000000

Inserted ahead of 9ae8275aebfd. That migration does
op.drop_index('ix_budget_usage_api_key_id', ...), but no index by that name
was ever created — budget_usage.api_key_id only ever got a differently-named
unique constraint (uq_budget_usage_api_key_id, from c3d4e5f6a7b8), so the
drop fails. This migration creates the index 9ae8275aebfd expects to find,
so its drop_index/create_unique_constraint pair can run as originally
written. 9ae8275aebfd itself is otherwise unchanged, apart from its
down_revision now pointing here instead of straight to d4e5f6a7b8c9.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36e2308271e1'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_budget_usage_api_key_id'), 'budget_usage', ['api_key_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_budget_usage_api_key_id'), table_name='budget_usage')
