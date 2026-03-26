"""add audio_lang_detection tables

Revision ID: 198c0fd8d490
Revises: 0fb1a4424704
Create Date: 2026-03-26 12:27:28.339059

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '198c0fd8d490'
down_revision: Union[str, None] = '0fb1a4424704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = inspect(bind).get_table_names()

    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    if 'audio_lang_detection_requests' not in existing_tables:
        op.create_table('audio_lang_detection_requests',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('api_key_id', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('model_id', sa.String(length=100), nullable=False),
        sa.Column('audio_duration', sa.Float(), nullable=True),
        sa.Column('processing_time', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['user_sessions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )

    if 'audio_lang_detection_results' not in existing_tables:
        op.create_table('audio_lang_detection_results',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('request_id', sa.UUID(), nullable=False),
        sa.Column('language_code', sa.String(length=50), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('all_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['request_id'], ['audio_lang_detection_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )


def downgrade() -> None:
    op.drop_table('audio_lang_detection_results')
    op.drop_table('audio_lang_detection_requests')
