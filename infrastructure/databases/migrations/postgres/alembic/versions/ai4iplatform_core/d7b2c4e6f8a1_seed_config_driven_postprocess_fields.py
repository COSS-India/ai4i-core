"""seed_config_driven_postprocess_fields

Adds the config-driven response-shaping fields (response_key / transform /
pair_with_input on outputs, and the response envelope block) to the
adapter_configs seeded by a1f2e3d4c5b6. The inference-service postprocess
overrides for six task types were replaced by this configuration, and NER's
JSON parsing moved to config while keeping its alignment algorithm
(ai4i-core PR #888) — without these fields the services return the generic
default shape instead of their task contract.

Values are merged into the existing adapter_config (jsonb read-modify-write
in Python) rather than overwritten, so environment-specific differences in
inputs/endpoints are preserved. Idempotent: re-running merges identical
values. Rows are keyed by mm_models.name exactly as stored (verified against
live data; see migration-checklist rule on backfill WHERE clauses).

Revision ID: d7b2c4e6f8a1
Revises: c3d5e7f9a2b4
Create Date: 2026-06-05 12:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd7b2c4e6f8a1'
down_revision: Union[str, None] = 'c3d5e7f9a2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


# model name (as stored in mm_models.name) ->
#   (per-output-index field additions, response envelope block)
ADAPTER_ADDITIONS = {
    "surya-ocr": (
        {0: {"response_key": "output[].source"}},
        {"static_item_fields": {"target": ""}},
    ),
    "transliteration": (
        {0: {"pair_with_input": "input.source"}},
        {"include_config": False},
    ),
    "indiclid": (
        {0: {"transform": ["json_parse", "wrap_list"],
             "pair_with_input": "input.source"}},
        {"include_config": False},
    ),
    "ald": (
        {2: {"transform": "json_parse"}},
        {"task_type": "audio-lang-detection", "config_keys": ["serviceId"]},
    ),
    "lang-diarization": (
        {0: {"transform": "json_parse", "response_key": "output[]"}},
        {"task_type": "language-diarization", "config_keys": ["serviceId"]},
    ),
    "asr-am-ensemble": (
        {0: {"response_key": "output[].source"}},
        {"include_config": False, "static_item_fields": {"nBestTokens": None}},
    ),
    # NER keeps its code postprocess (BPE/offset alignment) but the JSON
    # parsing of OUTPUT_TEXT moves to config: the algorithm consumes the
    # parsed object directly. No response envelope (the override shapes it).
    "ner": (
        {0: {"transform": "json_parse"}},
        None,
    ),
}

_RESPONSE_FIELDS = ("task_type", "include_config", "config_keys", "static_item_fields")
_OUTPUT_FIELDS = ("response_key", "transform", "pair_with_input")


def upgrade() -> None:
    conn = op.get_bind()

    for model_name, (output_adds, response_block) in ADAPTER_ADDITIONS.items():
        row = conn.execute(
            sa.text(
                "SELECT inference_endpoint->'adapterConfig' "
                "FROM mm_models WHERE name = :name"
            ),
            {"name": model_name},
        ).fetchone()
        if row is None or row[0] is None:
            # Model absent in this environment (e.g. partial registrations) —
            # nothing to shape; the service cannot resolve it anyway.
            print(f"  SKIP {model_name}: no mm_models row / adapterConfig")
            continue

        adapter = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        outputs = adapter.get("outputs") or []
        for idx, adds in output_adds.items():
            if idx >= len(outputs):
                raise RuntimeError(
                    f"{model_name}: adapterConfig has {len(outputs)} outputs, "
                    f"expected index {idx} — refusing to seed mismatched config"
                )
            outputs[idx].update(adds)
        if response_block is not None:
            adapter["response"] = response_block

        result = conn.execute(
            sa.text(
                "UPDATE mm_models SET inference_endpoint = "
                "jsonb_set(inference_endpoint, '{adapterConfig}', "
                "CAST(:cfg AS jsonb)) WHERE name = :name"
            ),
            {"cfg": json.dumps(adapter), "name": model_name},
        )
        if result.rowcount != 1:
            raise RuntimeError(
                f"{model_name}: expected to update 1 row, got {result.rowcount}"
            )
        print(f"  OK {model_name}: shaping fields merged")


def downgrade() -> None:
    conn = op.get_bind()

    for model_name, (output_adds, _response_block) in ADAPTER_ADDITIONS.items():
        row = conn.execute(
            sa.text(
                "SELECT inference_endpoint->'adapterConfig' "
                "FROM mm_models WHERE name = :name"
            ),
            {"name": model_name},
        ).fetchone()
        if row is None or row[0] is None:
            continue

        adapter = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        outputs = adapter.get("outputs") or []
        for idx in output_adds:
            if idx < len(outputs):
                for field in _OUTPUT_FIELDS:
                    outputs[idx].pop(field, None)
        adapter.pop("response", None)

        conn.execute(
            sa.text(
                "UPDATE mm_models SET inference_endpoint = "
                "jsonb_set(inference_endpoint, '{adapterConfig}', "
                "CAST(:cfg AS jsonb)) WHERE name = :name"
            ),
            {"cfg": json.dumps(adapter), "name": model_name},
        )
