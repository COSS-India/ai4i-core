"""migrate_asr_adapter_config_to_v2

Revision ID: a5b6c7d8e9f0
Revises: f4d5e6a7b8c9
Create Date: 2026-06-12 00:00:00.000000

Migrates ASR to the v2 (JSONata) schema (AI4IDS-1981). Byte-identical to the
current v1 output: the v1 config already shapes TRANSCRIPTS to the ULCA
contract (output[].source + constant nBestTokens), and the v2 output_transform
reproduces it. ASR keeps its float-PCM preprocessing code; only the config
changes. v1 snapshotted to mm_models_adapter_config_history; downgrade restores.
Keyed by mm_models.name 'asr-am-ensemble'. Idempotent.
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "f4d5e6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


_MODEL_NAME = "asr-am-ensemble"
_ASR_T = (
    '{ "output": [ $map(tensors.TRANSCRIPTS, function($t){ '
    '{"source": $t, "nBestTokens": null} }) ] }'
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


def _write(conn, name, cfg):
    res = conn.execute(
        sa.text(
            "UPDATE mm_models SET inference_endpoint = jsonb_set("
            "inference_endpoint, '{adapter_config}', CAST(:cfg AS jsonb)) "
            "WHERE name = :name"
        ),
        {"cfg": json.dumps(cfg), "name": name},
    )
    if res.rowcount != 1:
        raise RuntimeError(f"{name}: expected to update 1 row, got {res.rowcount}")


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

    conn.execute(
        sa.text(
            "INSERT INTO mm_models_adapter_config_history "
            "(model_id, version, schema_version, config) "
            "VALUES (:model_id, :version, :schema_version, CAST(:config AS jsonb))"
        ),
        {"model_id": model_id, "version": version,
         "schema_version": str(v1.get("version", "1")), "config": json.dumps(v1)},
    )

    v2 = {
        "schema_version": "2.0",
        "model_version": v1.get("model_version", "1"),
        "inputs": v1.get("inputs", []),
        "outputs": [{"tensor": o["tensor"]} for o in v1.get("outputs", [])],
        "output_transform": _ASR_T,
    }
    _write(conn, _MODEL_NAME, v2)
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
        raise RuntimeError(f"{_MODEL_NAME}: no v1 snapshot in history; cannot downgrade")
    v1 = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    _write(conn, _MODEL_NAME, v1)
    print(f"  OK {_MODEL_NAME}: adapter_config restored to v1 from history")
