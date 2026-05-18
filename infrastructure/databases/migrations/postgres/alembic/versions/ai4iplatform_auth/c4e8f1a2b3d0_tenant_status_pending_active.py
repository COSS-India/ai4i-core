"""Migrate tenant_status_enum to PENDING/ACTIVE/SUSPENDED/DEACTIVATED

Revision ID: c4e8f1a2b3d0
Revises: b66dd69a00df
Create Date: 2026-05-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4e8f1a2b3d0"
down_revision: Union[str, None] = "b66dd69a00df"
branch_labels: Union[str, Sequence[str]] = None
depends_on: Union[str, Sequence[str]] = None


def upgrade() -> None:
    op.execute(
        """
        DO $migration$
        DECLARE
            has_legacy_labels boolean;
        BEGIN
            SELECT EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'tenant_status_enum'
                  AND e.enumlabel IN ('activated', 'deactivated', 'suspended')
            ) INTO has_legacy_labels;

            IF has_legacy_labels THEN
                ALTER TYPE tenant_status_enum RENAME TO tenant_status_enum_old;
                CREATE TYPE tenant_status_enum AS ENUM (
                    'PENDING', 'ACTIVE', 'SUSPENDED', 'DEACTIVATED'
                );
                ALTER TABLE tenants ALTER COLUMN status DROP DEFAULT;
                ALTER TABLE tenants
                    ALTER COLUMN status TYPE tenant_status_enum
                    USING (
                        CASE status::text
                            WHEN 'activated' THEN 'ACTIVE'
                            WHEN 'deactivated' THEN 'DEACTIVATED'
                            WHEN 'suspended' THEN 'SUSPENDED'
                            ELSE 'ACTIVE'
                        END
                    )::tenant_status_enum;
                DROP TYPE tenant_status_enum_old;
                ALTER TABLE tenants ALTER COLUMN status SET DEFAULT 'PENDING';
            ELSE
                UPDATE tenants
                SET status = (
                    CASE status::text
                        WHEN 'activated' THEN 'ACTIVE'
                        WHEN 'deactivated' THEN 'DEACTIVATED'
                        WHEN 'suspended' THEN 'SUSPENDED'
                        ELSE status::text
                    END
                )::tenant_status_enum
                WHERE status::text IN ('activated', 'deactivated', 'suspended');
            END IF;
        END $migration$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $migration$
        BEGIN
            ALTER TYPE tenant_status_enum RENAME TO tenant_status_enum_old;
            CREATE TYPE tenant_status_enum AS ENUM (
                'activated', 'deactivated', 'suspended'
            );
            ALTER TABLE tenants ALTER COLUMN status DROP DEFAULT;
            ALTER TABLE tenants
                ALTER COLUMN status TYPE tenant_status_enum
                USING (
                    CASE status::text
                        WHEN 'ACTIVE' THEN 'activated'
                        WHEN 'DEACTIVATED' THEN 'deactivated'
                        WHEN 'SUSPENDED' THEN 'suspended'
                        WHEN 'PENDING' THEN 'activated'
                        ELSE 'activated'
                    END
                )::tenant_status_enum;
            DROP TYPE tenant_status_enum_old;
            ALTER TABLE tenants ALTER COLUMN status SET DEFAULT 'activated';
        END $migration$;
        """
    )
