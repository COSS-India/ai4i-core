"""add_ner_and_transliteration_adapter_config_to_mm_services

Revision ID: f7e8d9c0b1a2
Revises: e4f6a8b2c1d0
Create Date: 2026-05-23 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7e8d9c0b1a2"
down_revision: Union[str, None] = "e4f6a8b2c1d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NER_ADAPTER_CONFIG = {
    "version": "1.0",
    "model_version": "1",
    "inputs": [
        {
            "tensor": "INPUT_TEXT",
            "dtype": "BYTES",
            "shape": [-1, 1],
            "value_path": "input.source",
        },
        {
            "tensor": "LANG_ID",
            "dtype": "BYTES",
            "shape": [-1, 1],
            "value_path": "request.config.language.source_language",
        },
    ],
    "outputs": [
        {
            "tensor": "OUTPUT_TEXT",
            "dtype": "BYTES",
            "maps_to": "target",
        },
    ],
}

_TRANSLITERATION_ADAPTER_CONFIG = {
    "version": "1.0",
    "model_version": "1",
    "inputs": [
        {
            "tensor": "INPUT_TEXT",
            "dtype": "BYTES",
            "shape": [-1],
            "value_path": "input.source",
        },
        {
            "tensor": "INPUT_LANGUAGE_ID",
            "dtype": "BYTES",
            "shape": [-1],
            "value_path": "request.config.language.source_language",
        },
        {
            "tensor": "OUTPUT_LANGUAGE_ID",
            "dtype": "BYTES",
            "shape": [-1],
            "value_path": "request.config.language.target_language",
        },
        {
            "tensor": "IS_WORD_LEVEL",
            "dtype": "BOOL",
            "shape": [-1],
            "value_path": "request.config.is_word_level",
        },
        {
            "tensor": "TOP_K",
            "dtype": "UINT8",
            "shape": [-1],
            "value_path": "request.config.top_k",
        },
    ],
    "outputs": [
        {
            "tensor": "OUTPUT_TEXT",
            "dtype": "BYTES",
            "maps_to": "target",
        },
    ],
}

_LANGUAGE_DETECTION_ADAPTER_CONFIG = {
    "version": "1.0",
    "model_version": "1",
    "inputs": [
        {
            "tensor": "INPUT_TEXT",
            "dtype": "BYTES",
            "shape": [-1, 1],
            "value_path": "input.source",
        },
    ],
    "outputs": [
        {
            "tensor": "OUTPUT_TEXT",
            "dtype": "BYTES",
            "maps_to": "langPrediction",
        },
    ],
}

_SERVICE_ADAPTER_CONFIGS = (
    ("ner-gpu", _NER_ADAPTER_CONFIG),
    ("indic-xlit-cpu", _TRANSLITERATION_ADAPTER_CONFIG),
    ("ai4bharat/triton-transliteration", _TRANSLITERATION_ADAPTER_CONFIG),
    ("indiclid-gpu", _LANGUAGE_DETECTION_ADAPTER_CONFIG),
)


def upgrade() -> None:
    conn = op.get_bind()
    for service_name, adapter_config in _SERVICE_ADAPTER_CONFIGS:
        conn.execute(
            sa.text(
                "UPDATE mm_services SET adapter_config = CAST(:cfg AS jsonb) WHERE name = :name"
            ),
            {"cfg": json.dumps(adapter_config), "name": service_name},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for service_name, _ in _SERVICE_ADAPTER_CONFIGS:
        conn.execute(
            sa.text("UPDATE mm_services SET adapter_config = NULL WHERE name = :name"),
            {"name": service_name},
        )
