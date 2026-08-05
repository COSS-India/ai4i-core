"""convert_cached_data_to_jsonb_gin

Revision ID: 790badc042e1
Revises: 75a838d63699
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '790badc042e1'
down_revision: Union[str, None] = '75a838d63699'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # api_key.cached_data was added as plain JSON (75a838d6), but the
    # write-through cache flow patches individual fields in place
    # (jsonb_set / the `-` key-delete operator) — both JSONB-only in
    # Postgres. Convert in place; existing values round-trip as-is.
    op.alter_column(
        'api_key',
        'cached_data',
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using='cached_data::jsonb',
        existing_nullable=True,
    )
    op.create_index(
        'ix_api_key_cached_data_gin',
        'api_key',
        ['cached_data'],
        unique=False,
        postgresql_using='gin',
    )


def downgrade() -> None:
    op.drop_index('ix_api_key_cached_data_gin', table_name='api_key')
    op.alter_column(
        'api_key',
        'cached_data',
        type_=sa.JSON(),
        postgresql_using='cached_data::json',
        existing_nullable=True,
    )