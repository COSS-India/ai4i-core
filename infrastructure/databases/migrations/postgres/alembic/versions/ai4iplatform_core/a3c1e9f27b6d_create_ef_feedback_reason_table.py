"""create_ef_feedback_reason_table

Creates ef_feedback_reason ("ef_" = explicit feedback): the configurable
reason catalog backing GET /feedback/reasons (a map of task_type -> reasons).
This is Table 2 of 2 in the feedback design — ef_feedback (Table 1) already
exists (see 68e712f0d05b). Ships with default rows out of the box; adding or
editing a reason is a data change, not a code change.

Revision ID: a3c1e9f27b6d
Revises: 68e712f0d05b
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a3c1e9f27b6d'
down_revision: Union[str, Sequence[str], None] = '68e712f0d05b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ef_feedback_reason',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('code', sa.String(100), nullable=False),
        sa.Column('label', sa.String(255), nullable=False),
        sa.Column('label_i18n', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('task_type', 'code', name='uq_ef_feedback_reason_task_type_code'),
    )
    op.create_index('ix_ef_feedback_reason_task_type', 'ef_feedback_reason', ['task_type'])


def downgrade() -> None:
    op.drop_index('ix_ef_feedback_reason_task_type', table_name='ef_feedback_reason')
    op.drop_table('ef_feedback_reason')
