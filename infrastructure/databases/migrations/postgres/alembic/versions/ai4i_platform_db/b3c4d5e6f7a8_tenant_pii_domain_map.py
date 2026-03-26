"""tenant_id to PII domain_id mapping for /redact resolution

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa

revision = "b3c4d5e6f7a8"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_pii_domain_map (
            tenant_id VARCHAR(255) PRIMARY KEY,
            domain_id VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_tenant_pii_domain_map_domain_id
        ON tenant_pii_domain_map (domain_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tenant_pii_domain_map_domain_id;")
    op.execute("DROP TABLE IF EXISTS tenant_pii_domain_map;")
