"""add_budget_usage_api_key_id_index

Revision ID: 36e2308271e1
Revises: 9ae8275aebfd
Create Date: 2026-08-27 15:00:00.000000

Sits AFTER 9ae8275aebfd (not before, as originally written) — this branch
was reordered to avoid editing 9ae8275aebfd itself, which is a
pre-existing/committed migration file. Consequence: 9ae8275aebfd's own
op.drop_index('ix_budget_usage_api_key_id', ...) still runs before this
migration ever creates that index — no index by that name was ever
created (budget_usage.api_key_id only ever got a differently-named unique
constraint, uq_budget_usage_api_key_id, from c3d4e5f6a7b8) — so
9ae8275aebfd's drop_index will still fail the same way it originally did.
This migration no longer fixes that; it's now just a same-shape index add
that runs after the fact. The actual index-drop-order bug is unresolved
again and needs a separate fix.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36e2308271e1'
down_revision: Union[str, None] = '9ae8275aebfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_budget_usage_api_key_id'), 'budget_usage', ['api_key_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_budget_usage_api_key_id'), table_name='budget_usage')
