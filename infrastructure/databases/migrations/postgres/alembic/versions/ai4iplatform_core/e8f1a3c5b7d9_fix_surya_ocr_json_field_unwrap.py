"""fix_surya_ocr_json_field_unwrap

surya-ocr's OUTPUT_TEXT tensor was seeded (a1f2e3d4c5b6) without json_field,
so Surya's raw JSON envelope ({"success", "text_lines", "full_text",
"image_bbox"}) was never unwrapped before being renamed to output[].source
by d7b2c4e6f8a1's response_key — OCR responses returned the whole JSON blob
as "source" instead of the extracted text. ocr_service.py's own docstring
already documents json_field="full_text" as the intended behavior; the
seeded config just never matched it.

Value is merged into the existing adapter_config (jsonb read-modify-write
in Python) rather than overwritten, so other declared fields are preserved.
Idempotent: re-running merges the same value. Row is keyed by mm_models.name
exactly as stored (matches the key used by a1f2e3d4c5b6 / d7b2c4e6f8a1).

Revision ID: e8f1a3c5b7d9
Revises: c8d9e0f1a2b3
Create Date: 2026-07-21 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e8f1a3c5b7d9'
down_revision: Union[str, None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

_MODEL_NAME = "surya-ocr"
_OUTPUT_INDEX = 0
_JSON_FIELD = "full_text"


def upgrade() -> None:
    conn = op.get_bind()

    row = conn.execute(
        sa.text(
            "SELECT inference_endpoint->'adapter_config' "
            "FROM mm_models WHERE name = :name"
        ),
        {"name": _MODEL_NAME},
    ).fetchone()
    if row is None or row[0] is None:
        # Model absent in this environment (e.g. partial registrations) —
        # nothing to fix; the service cannot resolve it anyway.
        print(f"  SKIP {_MODEL_NAME}: no mm_models row / adapter_config")
        return

    adapter = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    outputs = adapter.get("outputs") or []
    if _OUTPUT_INDEX >= len(outputs):
        raise RuntimeError(
            f"{_MODEL_NAME}: adapter_config has {len(outputs)} outputs, "
            f"expected index {_OUTPUT_INDEX} — refusing to seed mismatched config"
        )
    outputs[_OUTPUT_INDEX]["json_field"] = _JSON_FIELD

    result = conn.execute(
        sa.text(
            "UPDATE mm_models SET inference_endpoint = "
            "jsonb_set(inference_endpoint, '{adapter_config}', "
            "CAST(:cfg AS jsonb)) WHERE name = :name"
        ),
        {"cfg": json.dumps(adapter), "name": _MODEL_NAME},
    )
    if result.rowcount != 1:
        raise RuntimeError(
            f"{_MODEL_NAME}: expected to update 1 row, got {result.rowcount}"
        )
    print(f"  OK {_MODEL_NAME}: json_field={_JSON_FIELD!r} merged into output[{_OUTPUT_INDEX}]")


def downgrade() -> None:
    conn = op.get_bind()

    row = conn.execute(
        sa.text(
            "SELECT inference_endpoint->'adapter_config' "
            "FROM mm_models WHERE name = :name"
        ),
        {"name": _MODEL_NAME},
    ).fetchone()
    if row is None or row[0] is None:
        return

    adapter = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    outputs = adapter.get("outputs") or []
    if _OUTPUT_INDEX < len(outputs):
        outputs[_OUTPUT_INDEX].pop("json_field", None)

    conn.execute(
        sa.text(
            "UPDATE mm_models SET inference_endpoint = "
            "jsonb_set(inference_endpoint, '{adapter_config}', "
            "CAST(:cfg AS jsonb)) WHERE name = :name"
        ),
        {"cfg": json.dumps(adapter), "name": _MODEL_NAME},
    )
