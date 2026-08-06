"""normalise_adapter_config_key_in_inference_endpoint

Migrations a1f2e3d4c5b6 and d7b2c4e6f8a1 stored the adapter configuration
under the key 'adapter_config' (snake_case) inside mm_models.inference_endpoint.
The application layer (serializers.py, model_service.py) always reads and writes
this key as 'adapterConfig' (camelCase), so ep.get("adapterConfig") was returning
None for every seeded row, causing the inference-service resolver to hit its
"adapter_config missing" warning path and fail to build Triton requests.

This migration renames the stored key to match what the application expects.

Revision ID: e7f8a9b0c1d2
Revises: c6e8a0b2d4f6
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'c6e8a0b2d4f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE mm_models
            SET inference_endpoint =
                (inference_endpoint - 'adapter_config')
                || jsonb_build_object('adapterConfig', inference_endpoint->'adapter_config')
            WHERE inference_endpoint ? 'adapter_config'
        """)
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE mm_models
            SET inference_endpoint =
                (inference_endpoint - 'adapterConfig')
                || jsonb_build_object('adapter_config', inference_endpoint->'adapterConfig')
            WHERE inference_endpoint ? 'adapterConfig'
        """)
    )
