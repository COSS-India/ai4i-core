"""create_inference_types_table

Catalogue of billable inference types (AI4IDS-2933 phase 1). DDL only — the
seed lives in the next revision so it can be rolled back independently.

Autogenerate also proposed a CREATE for ``ppu_tenant_tier_assignments`` and a
server_default change on ``mm_services.is_multilingual_enabled``. Both are
pre-existing model/DB drift unrelated to this change and were stripped.

Revision ID: 80d597c64a58
Revises: b2d4f6a8c0e1
Create Date: 2026-08-31 15:45:38.677136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '80d597c64a58'
down_revision: Union[str, None] = 'b2d4f6a8c0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'inference_types',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('endpoint_patterns', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('unit', sa.String(length=64), nullable=False),
        sa.Column('pricing', sa.String(length=64), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('updated_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_inference_types_name'),
    )


def downgrade() -> None:
    op.drop_table('inference_types')
