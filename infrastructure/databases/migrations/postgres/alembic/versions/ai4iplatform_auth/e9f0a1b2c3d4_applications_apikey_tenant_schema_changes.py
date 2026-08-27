"""applications_apikey_tenant_schema_changes

Adds applications table, budget columns to tenants, migrates api_key
from user_id ownership to application_id. Seeds one default application
per tenant and backfills existing api_key rows before enforcing NOT NULL.

Revision ID: e9f0a1b2c3d4
Revises: c5d6e7f8a9b1
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Add new columns to tenants
    op.add_column('tenants', sa.Column('tier_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('tenants', sa.Column('allocated_budget', sa.Numeric(15, 8), nullable=True))
    op.add_column('tenants', sa.Column('budget_effective_from', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tenants', sa.Column('budget_effective_to', sa.DateTime(timezone=True), nullable=True))

    # 2. Create application_status_enum type and applications table
    op.execute("CREATE TYPE application_status_enum AS ENUM ('ACTIVE', 'INACTIVE')")
    op.create_table(
        'applications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255), nullable=True),
        sa.Column('allocated_percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('allocated_budget', sa.Numeric(15, 8), nullable=True),
        sa.Column(
            'status',
            postgresql.ENUM('ACTIVE', 'INACTIVE', name='application_status_enum', create_type=False),
            nullable=False,
            server_default='ACTIVE',
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_applications_id'), 'applications', ['id'])
    op.create_index(op.f('ix_applications_tenant_id'), 'applications', ['tenant_id'])
    op.execute(
        "CREATE UNIQUE INDEX uq_applications_tenant_name_lower "
        "ON applications (tenant_id, lower(name))"
    )

    # 3. Seed one default application per existing tenant (idempotent)
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO applications (tenant_id, name, status, created_at)
        SELECT id, 'Default Application', 'ACTIVE', now()
        FROM tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM applications a
            WHERE a.tenant_id = t.id AND lower(a.name) = 'default application'
        )
    """))

    # 4. Add application_id as nullable first to allow backfill
    op.add_column('api_key', sa.Column('application_id', sa.Integer(), nullable=True))
    op.add_column('api_key', sa.Column('allocated_percentage', sa.Numeric(5, 2), nullable=True))
    op.add_column('api_key', sa.Column('allocated_budget', sa.Numeric(15, 8), nullable=True))

    # 5. Backfill application_id on existing api_key rows via user_id → users → tenant
    result = conn.execute(sa.text("""
        UPDATE api_key ak
        SET application_id = a.id
        FROM users u
        JOIN applications a
            ON a.tenant_id = u.tenant_id
            AND lower(a.name) = 'default application'
        WHERE ak.user_id = u.id
          AND ak.application_id IS NULL
    """))

    # Verify every api_key row resolved — a missed row would surface as an opaque NOT NULL violation
    unresolved = conn.execute(sa.text(
        "SELECT count(*) FROM api_key WHERE application_id IS NULL"
    )).scalar()
    if unresolved:
        raise RuntimeError(
            f"Backfill incomplete: {unresolved} api_key row(s) have no matching tenant application. "
            "Check that every api_key.user_id references a user with a valid tenant_id."
        )

    # 6. Enforce NOT NULL now that all rows are backfilled
    op.alter_column('api_key', 'application_id', nullable=False)

    # 7. Add FK and index on application_id
    # RESTRICT prevents silent cascade that would orphan budget_usage rows in the core DB
    # (cross-DB FK is not possible). When application-deletion service logic is implemented,
    # it must explicitly delete budget_usage rows for the affected api_key_ids before
    # deleting the api_keys themselves.
    op.create_index(op.f('ix_api_key_application_id'), 'api_key', ['application_id'])
    op.create_foreign_key(
        'api_key_application_id_fkey', 'api_key', 'applications',
        ['application_id'], ['id'], ondelete='RESTRICT',
    )

    # 8. Drop user_id FK, index, and column
    op.drop_index(op.f('ix_api_key_user_id'), table_name='api_key')
    op.drop_constraint('api_key_user_id_fkey', 'api_key', type_='foreignkey')
    op.drop_column('api_key', 'user_id')


def downgrade() -> None:
    # Restore user_id
    op.add_column('api_key', sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_api_key_user_id'), 'api_key', ['user_id'])
    op.create_foreign_key(
        'api_key_user_id_fkey', 'api_key', 'users',
        ['user_id'], ['id'], ondelete='CASCADE',
    )

    # Remove application_id columns
    op.drop_constraint('api_key_application_id_fkey', 'api_key', type_='foreignkey')
    op.drop_index(op.f('ix_api_key_application_id'), table_name='api_key')
    op.drop_column('api_key', 'allocated_budget')
    op.drop_column('api_key', 'allocated_percentage')
    op.drop_column('api_key', 'application_id')

    # Drop applications table and enum
    op.execute("DROP INDEX IF EXISTS uq_applications_tenant_name_lower")
    op.drop_index(op.f('ix_applications_tenant_id'), table_name='applications')
    op.drop_index(op.f('ix_applications_id'), table_name='applications')
    op.drop_table('applications')
    op.execute("DROP TYPE IF EXISTS application_status_enum")

    # Remove tenant columns
    op.drop_column('tenants', 'budget_effective_to')
    op.drop_column('tenants', 'budget_effective_from')
    op.drop_column('tenants', 'allocated_budget')
    op.drop_column('tenants', 'tier_id')
