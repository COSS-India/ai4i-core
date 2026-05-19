"""seed_default_data

Revision ID: 674e02c5e008
Revises: ccceb4ac886d
Create Date: 2026-05-18 15:50:04.649247

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '674e02c5e008'
down_revision: Union[str, None] = 'ccceb4ac886d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(r"""
        INSERT INTO data_enrichment_rules
            (rule_name, source_field, target_field, enrichment_type, configuration, is_active)
        VALUES
        (
            'Extract User ID from Trace', 'trace_id', 'user_id', 'extraction',
            '{"pattern": "user-([a-f0-9-]+)", "group": 1}'::jsonb, true
        ),
        (
            'Classify Log Level', 'log_level', 'severity', 'classification',
            '{"mapping": {"DEBUG": "low", "INFO": "low", "WARNING": "medium", "ERROR": "high", "CRITICAL": "critical"}}'::jsonb, true
        ),
        (
            'Extract Service Name', 'log_message', 'service_name', 'extraction',
            '{"pattern": "\\[([A-Za-z-]+)\\]", "group": 1}'::jsonb, true
        ),
        (
            'Add Environment Tag', 'metadata', 'environment', 'enrichment',
            '{"default": "production", "sources": ["kubernetes.namespace", "env.ENVIRONMENT"]}'::jsonb, true
        ),
        (
            'Correlate Request ID', 'request_id', 'correlation_id', 'correlation',
            '{"join_field": "request_id", "ttl_seconds": 3600}'::jsonb, true
        )
        ON CONFLICT (rule_name) DO NOTHING
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DELETE FROM data_enrichment_rules
        WHERE rule_name IN (
            'Extract User ID from Trace',
            'Classify Log Level',
            'Extract Service Name',
            'Add Environment Tag',
            'Correlate Request ID'
        )
    """))
