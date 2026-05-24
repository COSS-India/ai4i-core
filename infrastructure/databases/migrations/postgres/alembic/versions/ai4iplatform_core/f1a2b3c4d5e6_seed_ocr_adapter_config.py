"""seed_ocr_adapter_config

Revision ID: f1a2b3c4d5e6
Revises: e4f6a8b2c1d0
Create Date: 2026-05-24 12:30:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e4f6a8b2c1d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

_OCR_ADAPTER_CONFIG = {
    "version": "1",
    "model_version": "1",
    "inputs": [
        {"tensor": "IMAGE_DATA", "dtype": "BYTES", "shape": [-1, 1], "value": "image.image_content"},
    ],
    "outputs": [
        {"tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "text"},
    ],
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE mm_services SET adapter_config = CAST(:cfg AS jsonb) WHERE name = :name"
        ),
        {"cfg": json.dumps(_OCR_ADAPTER_CONFIG), "name": "surya-ocr-gpu"},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE mm_services SET adapter_config = NULL WHERE name = :name"),
        {"name": "surya-ocr-gpu"},
    )
