"""ulca_conform_mm_services

Brings mm_services into line with the ULCA Service schema: adds
version/ref_url/task/languages/license/domain/submitter/training_dataset,
and replaces the flat endpoint/api_key columns with a single
inference_endpoint JSONB column (ULCA InferenceAPIEndPoint shape —
callbackUrl/inferenceApiKey/schema/...).

New columns are nullable at the DB layer (existing rows have no value yet);
ServiceCreateRequest enforces them as required for new services at the
application layer.

Revision ID: a3f9c2e7b1d4
Revises: e8f1a3c5b7d9
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a3f9c2e7b1d4'
down_revision: Union[str, None] = 'e8f1a3c5b7d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column('mm_services', sa.Column('version', sa.String(length=20), nullable=True))
    op.add_column('mm_services', sa.Column('ref_url', sa.String(length=200), nullable=True))
    op.add_column('mm_services', sa.Column('task', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('mm_services', sa.Column('languages', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('mm_services', sa.Column('license', sa.String(length=255), nullable=True))
    op.add_column('mm_services', sa.Column('domain', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('mm_services', sa.Column('submitter', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('mm_services', sa.Column('training_dataset', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('mm_services', sa.Column('inference_endpoint', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE mm_services SET inference_endpoint = jsonb_build_object("
            "'callbackUrl', endpoint, "
            "'inferenceApiKey', CASE WHEN api_key IS NOT NULL "
            "THEN jsonb_build_object('name', 'Authorization', 'value', api_key) "
            "ELSE NULL END, "
            "'schema', '[]'::jsonb)"
        )
    )

    op.drop_column('mm_services', 'endpoint')
    op.drop_column('mm_services', 'api_key')


def downgrade() -> None:
    op.add_column('mm_services', sa.Column('api_key', sa.String(length=255), nullable=True))
    op.add_column('mm_services', sa.Column('endpoint', sa.String(length=500), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE mm_services SET "
            "endpoint = inference_endpoint->>'callbackUrl', "
            "api_key = inference_endpoint->'inferenceApiKey'->>'value'"
        )
    )

    op.drop_column('mm_services', 'inference_endpoint')
    op.drop_column('mm_services', 'training_dataset')
    op.drop_column('mm_services', 'submitter')
    op.drop_column('mm_services', 'domain')
    op.drop_column('mm_services', 'license')
    op.drop_column('mm_services', 'languages')
    op.drop_column('mm_services', 'task')
    op.drop_column('mm_services', 'ref_url')
    op.drop_column('mm_services', 'version')
