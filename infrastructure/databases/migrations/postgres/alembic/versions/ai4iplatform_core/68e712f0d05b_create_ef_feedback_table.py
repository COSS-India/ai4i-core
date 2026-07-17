"""create_ef_feedback_table

Creates ef_feedback ("ef_" = explicit feedback): one row per thumbs up/down
submission for the Explicit Feedback API (v0.1). Persistent — not
time-limited. Every row is tagged to request_id + model_provider +
model_version for cross-version comparison. One feedback per request_id
(enforced by the unique constraint); a duplicate submission updates the
existing row via ON CONFLICT DO UPDATE (see FeedbackRepository).

This is Table 1 of 2 in the feedback design — ef_feedback_reason (the
configurable reason catalog backing GET /feedback/reasons) is a separate,
later migration. Reason codes are stored as free strings here until that
table exists and is seeded.

Revision ID: 68e712f0d05b
Revises: c8d9e0f1a2b3
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '68e712f0d05b'
down_revision: Union[str, Sequence[str], None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ef_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('request_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_task_type', sa.String(50), nullable=False),
        sa.Column(
            'feedback_type',
            sa.Enum('THUMBS', name='feedback_type'),
            nullable=False,
        ),
        sa.Column(
            'rating',
            sa.Enum('POSITIVE', 'NEGATIVE', name='feedback_rating'),
            nullable=False,
        ),
        sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('corrected_output', sa.Text(), nullable=True),
        sa.Column('model_provider', sa.String(255), nullable=False),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('tenant_id', sa.String(255), nullable=True),
        sa.Column('source_language', sa.String(20), nullable=True),
        sa.Column('target_language', sa.String(20), nullable=True),
        sa.Column('language_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('feedback_language', sa.String(20), nullable=True),
        sa.Column('feedback_source', sa.String(30), nullable=False, server_default='API'),
        sa.Column('model_id', sa.String(255), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('request_id', name='uq_ef_feedback_request_id'),
    )
    op.create_index('ix_ef_feedback_request_id', 'ef_feedback', ['request_id'])
    op.create_index('ix_ef_feedback_model_task_type', 'ef_feedback', ['model_task_type'])
    op.create_index('ix_ef_feedback_tenant_id', 'ef_feedback', ['tenant_id'])
    op.create_index(
        'ix_ef_feedback_provider_version', 'ef_feedback', ['model_provider', 'model_version']
    )
    op.create_index(
        'ix_ef_feedback_task_type_created_at', 'ef_feedback', ['model_task_type', 'created_at']
    )


def downgrade() -> None:
    op.drop_index('ix_ef_feedback_task_type_created_at', table_name='ef_feedback')
    op.drop_index('ix_ef_feedback_provider_version', table_name='ef_feedback')
    op.drop_index('ix_ef_feedback_tenant_id', table_name='ef_feedback')
    op.drop_index('ix_ef_feedback_model_task_type', table_name='ef_feedback')
    op.drop_index('ix_ef_feedback_request_id', table_name='ef_feedback')
    op.drop_table('ef_feedback')

    # create_table's inline sa.Enum() auto-creates these PG enum types;
    # drop_table does not drop them — must be dropped explicitly.
    op.execute('DROP TYPE feedback_rating')
    op.execute('DROP TYPE feedback_type')
