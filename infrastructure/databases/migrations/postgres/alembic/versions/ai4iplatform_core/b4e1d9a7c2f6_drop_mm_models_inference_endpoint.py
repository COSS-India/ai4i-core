"""drop_mm_models_inference_endpoint

The ULCA Service.inferenceEndPoint is the live, callable endpoint — it does
not belong on Model (AI4IDS-2478 review). Before dropping mm_models.
inference_endpoint, best-effort carries its adapter_config and declared
Triton model_name forward onto every mm_services row that references that
(model_id, version), merged into mm_services.inference_endpoint as
adapterConfig/inferenceModelId respectively.

Revision ID: b4e1d9a7c2f6
Revises: a3f9c2e7b1d4
Create Date: 2026-07-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b4e1d9a7c2f6'
down_revision: Union[str, None] = 'a3f9c2e7b1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE mm_services s "
            "SET inference_endpoint = COALESCE(s.inference_endpoint, '{}'::jsonb) || "
            "jsonb_strip_nulls(jsonb_build_object("
            "'adapterConfig', m.inference_endpoint->'adapter_config', "
            "'inferenceModelId', m.inference_endpoint->'schema'->>'model_name'"
            ")) "
            "FROM mm_models m "
            "WHERE s.model_id = m.model_id AND s.model_version = m.version "
            "AND m.inference_endpoint IS NOT NULL"
        )
    )
    op.drop_column('mm_models', 'inference_endpoint')


def downgrade() -> None:
    # Lossy: adapter_config/model_name were merged onto (potentially many)
    # mm_services rows, not restorable 1:1 back onto mm_models.
    op.add_column(
        'mm_models',
        sa.Column('inference_endpoint', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
