"""migrate_nmt_adapter_config_to_v2

Revision ID: c1a2b3d4e5f6
Revises: b1c2d3e4f5a6
Create Date: 2026-06-12 00:00:00.000000

Migrates the NMT model's adapter_config to the v2 (JSONata) schema
(AI4IDS-1981). The v1 typed inputs are preserved; the v1 output declaration
(maps_to / shaping) is replaced by a single output_transform expression that
the inference-service runs via JSONata. The prior v1 config is snapshotted into
mm_models_adapter_config_history first, and downgrade restores it.

Keyed by mm_models.name 'indictrans' (verified against live data). Idempotent:
skips a row already on schema_version 2.0.
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


_MODEL_NAME = "indictrans"

# NMT task-type output contract: pair each translated OUTPUT_TEXT with the
# input source (the v1 default postprocess produced the same {source, target}).
_NMT_OUTPUT_TRANSFORM = (
    "( $inp := inputs; "
    "{ \"output\": [ $map(tensors.OUTPUT_TEXT, function($t, $i) "
    "{ {\"source\": $inp[$i].source, \"target\": $t} }) ] } )"
)


def _load(conn, name):
    row = conn.execute(
        sa.text(
            "SELECT model_id, version, inference_endpoint->'adapter_config' "
            "FROM mm_models WHERE name = :name"
        ),
        {"name": name},
    ).fetchone()
    if row is None or row[2] is None:
        return None
    cfg = row[2] if isinstance(row[2], dict) else json.loads(row[2])
    return row[0], row[1], cfg


def _write_config(conn, name, cfg):
    result = conn.execute(
        sa.text(
            "UPDATE mm_models SET inference_endpoint = jsonb_set("
            "inference_endpoint, '{adapter_config}', CAST(:cfg AS jsonb)) "
            "WHERE name = :name"
        ),
        {"cfg": json.dumps(cfg), "name": name},
    )
    if result.rowcount != 1:
        raise RuntimeError(f"{name}: expected to update 1 row, got {result.rowcount}")


def upgrade() -> None:
    conn = op.get_bind()
    loaded = _load(conn, _MODEL_NAME)
    if loaded is None:
        print(f"  SKIP {_MODEL_NAME}: no mm_models row / adapter_config")
        return
    model_id, version, v1 = loaded

    if str(v1.get("schema_version", "")).startswith("2"):
        print(f"  SKIP {_MODEL_NAME}: already v2")
        return

    # Snapshot the v1 config for rollback.
    conn.execute(
        sa.text(
            "INSERT INTO mm_models_adapter_config_history "
            "(model_id, version, schema_version, config) "
            "VALUES (:model_id, :version, :schema_version, CAST(:config AS jsonb))"
        ),
        {"model_id": model_id, "version": version,
         "schema_version": str(v1.get("version", "1")), "config": json.dumps(v1)},
    )

    # Build v2 from v1: preserve typed inputs; outputs become decode hints;
    # the shaping moves to output_transform.
    v2 = {
        "schema_version": "2.0",
        "model_version": v1.get("model_version", "1"),
        "inputs": v1.get("inputs", []),
        "outputs": [{"tensor": o["tensor"]} for o in v1.get("outputs", [])],
        "output_transform": _NMT_OUTPUT_TRANSFORM,
    }
    _write_config(conn, _MODEL_NAME, v2)
    print(f"  OK {_MODEL_NAME}: adapter_config migrated to v2")


def downgrade() -> None:
    conn = op.get_bind()
    loaded = _load(conn, _MODEL_NAME)
    if loaded is None:
        return
    model_id, _version, _cfg = loaded

    row = conn.execute(
        sa.text(
            "SELECT config FROM mm_models_adapter_config_history "
            "WHERE model_id = :model_id ORDER BY archived_at DESC, id DESC LIMIT 1"
        ),
        {"model_id": model_id},
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"{_MODEL_NAME}: no v1 snapshot in history to restore; cannot downgrade"
        )
    v1 = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    _write_config(conn, _MODEL_NAME, v1)
    print(f"  OK {_MODEL_NAME}: adapter_config restored to v1 from history")
