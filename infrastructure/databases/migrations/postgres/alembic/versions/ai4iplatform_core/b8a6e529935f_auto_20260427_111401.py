"""auto_20260427_111401

Revision ID: b8a6e529935f
Revises: 1df5f5c5f309
Create Date: 2026-04-27 11:14:01.624140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8a6e529935f'
down_revision: Union[str, None] = '1df5f5c5f309'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the FK on mm_services first — it depends on ix_mm_models_model_id
    # and must be removed before we can drop/recreate that index.
    op.drop_constraint('mm_services_model_id_fkey', 'mm_services', type_='foreignkey')

    # ── mm_models ─────────────────────────────────────────────────────────────
    # Rename the enum type to match current ORM definition
    op.execute("ALTER TYPE version_status_enum RENAME TO version_status")

    # Drop old unique index on model_id; replace with named unique constraint + plain index
    # (ix_mm_models_model_id was unique=True; now index=True produces a non-unique index)
    op.drop_index('ix_mm_models_model_id', table_name='mm_models')
    op.create_index('ix_mm_models_model_id', 'mm_models', ['model_id'], unique=False)
    op.create_unique_constraint('uq_mm_models_model_id', 'mm_models', ['model_id'])

    # uq_mm_models_name_version already has the correct name from migration 1 — no rename needed

    # Add indexes expected by the ORM model
    op.create_index('ix_mm_models_name', 'mm_models', ['name'], unique=False)
    op.create_index('ix_mm_models_created_by', 'mm_models', ['created_by'], unique=False)

    # Make timestamps NOT NULL
    op.alter_column('mm_models', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('mm_models', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))

    # ── mm_services ───────────────────────────────────────────────────────────
    # Recreate the FK with an explicit mm-prefixed name
    op.create_foreign_key('fk_mm_services_model_id', 'mm_services', 'mm_models',
                          ['model_id'], ['model_id'], ondelete='RESTRICT')

    # Drop old unique index on service_id; replace with named unique constraint + plain index
    op.drop_index('ix_mm_services_service_id', table_name='mm_services')
    op.create_index('ix_mm_services_service_id', 'mm_services', ['service_id'], unique=False)
    op.create_unique_constraint('uq_mm_services_service_id', 'mm_services', ['service_id'])

    # ix_mm_services_model_id already has the correct name — no rename needed

    # Rename the auto-named name unique constraint to an explicit mm-prefixed name
    op.drop_constraint('mm_services_name_key', 'mm_services', type_='unique')
    op.create_unique_constraint('uq_mm_services_name', 'mm_services', ['name'])

    # Add indexes expected by the ORM model
    op.create_index('ix_mm_services_is_published', 'mm_services', ['is_published'], unique=False)
    op.create_index('ix_mm_services_created_by', 'mm_services', ['created_by'], unique=False)

    # Set server_default for is_published
    op.alter_column('mm_services', 'is_published',
               existing_type=sa.BOOLEAN(),
               server_default='false',
               existing_nullable=False)

    # Make timestamps NOT NULL
    op.alter_column('mm_services', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('mm_services', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))


def downgrade() -> None:
    # Drop the FK first — it depends on uq_mm_models_model_id which we'll drop below
    op.drop_constraint('fk_mm_services_model_id', 'mm_services', type_='foreignkey')

    # ── mm_services ───────────────────────────────────────────────────────────
    op.alter_column('mm_services', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.alter_column('mm_services', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.alter_column('mm_services', 'is_published',
               existing_type=sa.BOOLEAN(),
               server_default=None,
               existing_nullable=False)
    op.drop_index('ix_mm_services_created_by', table_name='mm_services')
    op.drop_index('ix_mm_services_is_published', table_name='mm_services')
    op.drop_constraint('uq_mm_services_name', 'mm_services', type_='unique')
    op.create_unique_constraint('mm_services_name_key', 'mm_services', ['name'])
    op.drop_constraint('uq_mm_services_service_id', 'mm_services', type_='unique')
    op.drop_index('ix_mm_services_service_id', table_name='mm_services')
    op.create_index('ix_mm_services_service_id', 'mm_services', ['service_id'], unique=True)
    op.create_foreign_key(None, 'mm_services', 'mm_models',
                          ['model_id'], ['model_id'], ondelete='RESTRICT')

    # ── mm_models ─────────────────────────────────────────────────────────────
    op.alter_column('mm_models', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.alter_column('mm_models', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.drop_index('ix_mm_models_created_by', table_name='mm_models')
    op.drop_index('ix_mm_models_name', table_name='mm_models')
    op.drop_constraint('uq_mm_models_model_id', 'mm_models', type_='unique')
    op.drop_index('ix_mm_models_model_id', table_name='mm_models')
    op.create_index('ix_mm_models_model_id', 'mm_models', ['model_id'], unique=True)
    op.execute("ALTER TYPE version_status RENAME TO version_status_enum")
