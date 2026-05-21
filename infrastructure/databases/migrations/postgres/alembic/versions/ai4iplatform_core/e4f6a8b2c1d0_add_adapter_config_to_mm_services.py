"""add_adapter_config_to_mm_services

Revision ID: e4f6a8b2c1d0
Revises: d3e850228f7e
Create Date: 2026-05-21 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e4f6a8b2c1d0'
down_revision: Union[str, None] = 'd3e850228f7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

_NMT_ADAPTER_CONFIG = {
    "version": "1.0",
    "model_version": "1",
    "inputs": [
        {"tensor": "INPUT_TEXT",         "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
        {"tensor": "INPUT_LANGUAGE_ID",  "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.source_language"},
        {"tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.target_language"},
    ],
    "outputs": [
        {"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target"},
    ],
}


def upgrade() -> None:
    op.add_column(
        "mm_services",
        sa.Column("adapter_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE mm_services SET adapter_config = CAST(:cfg AS jsonb) WHERE name = :name"
        ),
        {"cfg": json.dumps(_NMT_ADAPTER_CONFIG), "name": "indictrans-gpu-t4"},
    )


def downgrade() -> None:
    op.drop_column("mm_services", "adapter_config")
